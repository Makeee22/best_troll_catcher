"""Optional signal: texts that are nearly the same (reworded copies) become one shared item.

    python -m swarm.similar download [MODEL]   # fetch the model once, e.g. while building a server image
"""
import functools
import sys
import threading

from .load import InputError

ENGLISH_MODEL = "minishlab/potion-base-8M"  # 30 MB
MULTILINGUAL_MODEL = "minishlab/potion-multilingual-128M"  # 512 MB download, about 2 GB of memory while loading
MODEL = MULTILINGUAL_MODEL
# Cosine at which two texts count as one. Among 20,000 background texts the multilingual model finds 293 pairs at 0.9,
# the English one 3,087. A looser cut (0.8) chains the synthetic sample's texts into one group of over 200, so it stays.
THRESHOLD = 0.9
MAX_TEXTS = 1_000_000
# Up to this many texts every pair is compared; above it random-projection hashing picks the pairs to compare.
EXACT_TEXTS = 50_000
# Hashing: TABLES independent tables of BITS random hyperplanes. Two texts at cosine 0.9 share a bucket in one table with
# probability 0.857**16 = 0.085, so 48 tables find 98.6% of such pairs and nearly all closer ones (99.9% at 0.95).
TABLES, BITS, SMALL = 48, 16, 32
# Near-duplicate pairs allowed before the signal is skipped: a templated dataset would otherwise run for minutes.
MAX_PAIRS = 20_000_000
# Largest group of texts that counts as one item; a bigger one is generic text chained together, not a copy.
MAX_GROUP = 200
BLOCK = 1000
GATHER = 100_000
_load_lock = threading.Lock()


@functools.lru_cache(maxsize=2)
def _load(name):
    from model2vec import StaticModel
    return StaticModel.from_pretrained(name)


def _model(name):
    """The loaded model, kept for the life of the process: a server loads it once, not once per analysis."""
    with _load_lock:  # two concurrent jobs must not both load a 2 GB model
        return _load(name)


_model.cache_clear = _load.cache_clear


class _TooManyPairs(Exception):
    pass


def _all_pairs(vectors, threshold, limit):
    """Every pair of rows at cosine >= threshold, compared block by block: (rows, cols) index arrays per block."""
    import numpy as np
    count = len(vectors)
    for start in range(0, count, BLOCK):
        block = vectors[start:start + BLOCK]
        hit = (block @ vectors[start:].T) >= threshold  # earlier columns were done by earlier blocks
        # Count before extracting indices, so a templated dataset cannot allocate hundreds of millions of them.
        # The block's own lower triangle and diagonal (at most BLOCK * (BLOCK + 1) / 2 hits) are not pairs.
        if int(np.count_nonzero(hit)) - len(block) * (len(block) + 1) // 2 > limit:
            raise _TooManyPairs
        rows, cols = np.nonzero(hit)
        keep = cols > rows  # each pair once, not the diagonal (row r and column c are texts start + r and start + c)
        yield rows[keep] + start, cols[keep] + start


def _hashed_pairs(vectors, threshold, limit, tables=TABLES, bits=BITS, small=SMALL, seed=0):
    """Pairs at cosine >= threshold among rows that share a bucket in some table; a pair may come more than once."""
    import numpy as np
    rng = np.random.default_rng(seed)  # fixed, so a rerun gives the same result
    count, weights = len(vectors), (1 << np.arange(bits)).astype(np.int64)
    for _ in range(tables):
        codes = ((vectors @ rng.standard_normal((vectors.shape[1], bits)).astype(np.float32)) > 0).astype(np.int64) @ weights
        order = np.argsort(codes, kind="stable")
        sorted_codes = codes[order]
        starts = np.flatnonzero(np.r_[True, sorted_codes[1:] != sorted_codes[:-1]])
        sizes = np.diff(np.r_[starts, count])
        size_at = np.repeat(sizes, sizes)  # bucket size at each sorted position
        # small buckets: compare each position with the next few in the same bucket, all buckets at once
        for d in range(1, min(small, count)):
            p = np.flatnonzero((size_at[:-d] <= small) & (sorted_codes[:-d] == sorted_codes[d:]))
            if not len(p):
                break
            a, b = order[p], order[p + d]
            hit = np.concatenate([np.einsum("ij,ij->i", vectors[a[i:i + GATHER]], vectors[b[i:i + GATHER]]) >= threshold
                                  for i in range(0, len(a), GATHER)])  # in chunks: a million texts would gather ~2 GB at once
            yield np.minimum(a, b)[hit], np.maximum(a, b)[hit]
        # large buckets: every pair inside, block by block
        for start, size in zip(starts[sizes > small].tolist(), sizes[sizes > small].tolist()):
            members = order[start:start + size]
            for rows, cols in _all_pairs(vectors[members], threshold, limit):
                yield members[rows], members[cols]


def add_items(con, model=None, threshold=THRESHOLD, max_texts=MAX_TEXTS, max_pairs=MAX_PAIRS, max_group=MAX_GROUP):
    """Add rows of kind `similar_text` to `item`. Needs the table `text_norm(key, norm)` made by detect.

    Returns (reason, warnings): `reason` says why the signal was skipped, or is None when it ran.
    """
    model = model or MODEL
    count = con.execute("select count(*) from text_norm").fetchall()[0][0]
    if count < 2:
        return "fewer than 2 distinct texts to compare", []
    if count > max_texts:
        return f"{count:,} distinct texts is more than the limit of {max_texts:,}", []
    try:  # optional dependencies: the rest of the core must import without them
        import numpy as np
        import model2vec  # noqa: F401
    except ImportError:
        raise InputError("the similar-text signal needs the model2vec package: pip install model2vec") from None
    keys, norms = zip(*con.execute("select key, norm from text_norm order by key").fetchall())
    try:
        vectors = _model(model).encode(list(norms)).astype(np.float32)
    except Exception as e:  # download or load failure: offline, unknown model name, disk full
        raise InputError(f"cannot load the similar-text model {model}: {str(e).splitlines()[0][:200] if str(e) else type(e).__name__}") from None
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.where(lengths == 0, 1, lengths)

    parent = list(range(count))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = raw = 0
    warnings = []
    hashed = count > EXACT_TEXTS
    try:
        # Exact: every pair comes once. Hashed: a close pair comes once per table that finds it (about 13 times, up to 48),
        # so only unions that join two groups count toward max_pairs, and the raw yields get their own cap.
        for rows, cols in (_hashed_pairs(vectors, threshold, max_pairs) if hashed else _all_pairs(vectors, threshold, max_pairs)):
            raw += len(rows)
            if not hashed:
                pairs = raw
            if raw > max_pairs * (TABLES if hashed else 1):
                raise _TooManyPairs
            for r, c in zip(rows.tolist(), cols.tolist()):
                a, b = find(r), find(c)
                if a != b:
                    parent[a] = b
                    pairs += hashed
            if pairs > max_pairs:
                raise _TooManyPairs
    except _TooManyPairs:
        return f"more than {max_pairs:,} near-duplicate text pairs (templated data?)", []
    if hashed:
        warnings.append(f"similar_text: {count:,} texts compared by random-projection hashing, which finds about 98.6% "
                        f"of the pairs at cosine {threshold} and nearly all closer ones")

    groups = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    too_big = sum(1 for g in groups.values() if len(g) > max_group)
    if too_big:
        warnings.append(f"similar_text: left out {too_big} groups of more than {max_group} similar texts (generic text chained together)")
    members = [(keys[i], gkey) for g in groups.values() if 2 <= len(g) <= max_group
               for gkey in [min(keys[j] for j in g)] for i in g]
    if members:
        con.execute("create or replace temp table text_group as select unnest(?::UBIGINT[]) as key, unnest(?::UBIGINT[]) as gkey",
                    [[m[0] for m in members], [m[1] for m in members]])
        # Word-for-word copies in a group are counted under `text` as well: recall matters more than counting once.
        con.execute("""
            insert into item (username, kind, key, value, first_seen, last_seen)
            select i.username, 'similar_text', g.gkey, first(i.value order by i.first_seen nulls last, i.value),
                   min(i.first_seen), max(i.last_seen)
            from item i join text_group g on i.key = g.key
            where i.kind = 'text'
            group by i.username, g.gkey""")
    return None, warnings


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "download":
        sys.exit("usage: python -m swarm.similar download [MODEL]")
    name = sys.argv[2] if len(sys.argv) > 2 else MODEL
    _model(name)
    print(f"model {name} is in the local cache")
