"""Optional signal: texts that are nearly the same (reworded copies) become one shared item."""
import numpy as np

from .load import InputError

MODEL = "minishlab/potion-base-8M"  # English; "minishlab/potion-multilingual-128M" for other languages
THRESHOLD = 0.9
MAX_TEXTS = 100_000
BLOCK = 1000


def add_items(con, model=MODEL, threshold=THRESHOLD, max_texts=MAX_TEXTS):
    """Add rows of kind `similar_text` to `item`. Needs the table `text_norm(key, norm)` made by detect."""
    count = con.execute("select count(*) from text_norm").fetchall()[0][0]
    if count > max_texts:
        return [f"similar_text skipped: {count:,} distinct texts is more than the limit of {max_texts:,}"]
    if count < 2:
        return []
    try:
        from model2vec import StaticModel
    except ImportError:
        raise InputError("the similar-text signal needs the model2vec package: pip install model2vec") from None
    keys, norms = zip(*con.execute("select key, norm from text_norm order by key").fetchall())
    vectors = StaticModel.from_pretrained(model).encode(list(norms)).astype(np.float32)
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.where(lengths == 0, 1, lengths)

    parent = list(range(count))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # shortcut: all-against-all comparison, fine to 100,000 distinct texts; use an approximate-neighbour index beyond that
    for start in range(0, count, BLOCK):
        sims = vectors[start:start + BLOCK] @ vectors.T
        rows, cols = np.nonzero(sims >= threshold)
        for r, c in zip(rows + start, cols):
            if c > r:
                parent[find(int(r))] = find(int(c))

    groups = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    pairs = [(keys[i], min(keys[j] for j in g)) for g in groups.values() if len(g) >= 2 for i in g]
    if pairs:
        con.execute("create or replace temp table text_group as select unnest(?::UBIGINT[]) as key, unnest(?::UBIGINT[]) as gkey",
                    [[p[0] for p in pairs], [p[1] for p in pairs]])
        con.execute("""
            insert into item
            select i.username, 'similar_text', g.gkey, first(i.value order by i.first_seen nulls last, i.value),
                   min(i.first_seen), max(i.last_seen)
            from item i join text_group g on i.key = g.key
            where i.kind = 'text'
            group by i.username, g.gkey""")
    return []
