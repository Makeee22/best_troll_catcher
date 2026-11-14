"""Optional signal: texts that are nearly the same (reworded copies) become one shared item."""
from .load import InputError

MODEL = "minishlab/potion-base-8M"  # English; "minishlab/potion-multilingual-128M" for other languages
THRESHOLD = 0.9
MAX_TEXTS = 100_000
# Near-duplicate pairs allowed before the signal is skipped: a templated dataset would otherwise run for minutes.
MAX_PAIRS = 20_000_000
# Largest group of texts that counts as one item; a bigger one is generic text chained together, not a copy.
MAX_GROUP = 200
BLOCK = 1000


def add_items(con, model=MODEL, threshold=THRESHOLD, max_texts=MAX_TEXTS, max_pairs=MAX_PAIRS, max_group=MAX_GROUP):
    """Add rows of kind `similar_text` to `item`. Needs the table `text_norm(key, norm)` made by detect.

    Returns (reason, warnings): `reason` says why the signal was skipped, or is None when it ran.
    """
    count = con.execute("select count(*) from text_norm").fetchall()[0][0]
    if count < 2:
        return "fewer than 2 distinct texts to compare", []
    if count > max_texts:
        return f"{count:,} distinct texts is more than the limit of {max_texts:,}", []
    try:  # optional dependencies: the rest of the core must import without them
        import numpy as np
        from model2vec import StaticModel
    except ImportError:
        raise InputError("the similar-text signal needs the model2vec package: pip install model2vec") from None
    keys, norms = zip(*con.execute("select key, norm from text_norm order by key").fetchall())
    try:
        vectors = StaticModel.from_pretrained(model).encode(list(norms)).astype(np.float32)
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

    pairs = 0
    # shortcut: all-against-all comparison, fine to 100,000 distinct texts; use an approximate-neighbour index beyond that
    for start in range(0, count, BLOCK):
        sims = vectors[start:start + BLOCK] @ vectors.T
        rows, cols = np.nonzero(sims >= threshold)
        keep = cols > rows + start  # each pair once, not the diagonal
        rows, cols = rows[keep] + start, cols[keep]
        pairs += len(rows)
        if pairs > max_pairs:
            return f"more than {max_pairs:,} near-duplicate text pairs (templated data?)", []
        for r, c in zip(rows.tolist(), cols.tolist()):
            parent[find(r)] = find(c)

    groups = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    warnings = []
    too_big = sum(1 for g in groups.values() if len(g) > max_group)
    if too_big:
        warnings.append(f"similar_text: left out {too_big} groups of more than {max_group} similar texts (generic text chained together)")
    members = [(keys[i], min(keys[j] for j in g)) for g in groups.values() if 2 <= len(g) <= max_group for i in g]
    if members:
        con.execute("create or replace temp table text_group as select unnest(?::UBIGINT[]) as key, unnest(?::UBIGINT[]) as gkey",
                    [[m[0] for m in members], [m[1] for m in members]])
        # Only groups with a text that nobody else posted word for word: groups of exact copies are already linked by `text`.
        con.execute("""
            insert into item
            with df as (select key, count(*) as df from item where kind = 'text' group by key),
            keep as (select g.gkey from text_group g join df using (key) group by g.gkey having min(df.df) = 1)
            select i.username, 'similar_text', g.gkey, first(i.value order by i.first_seen nulls last, i.value),
                   min(i.first_seen), max(i.last_seen)
            from item i join text_group g on i.key = g.key
            where i.kind = 'text' and g.gkey in (select gkey from keep)
            group by i.username, g.gkey""")
    return None, warnings
