import hashlib

from . import similar
from .load import InputError

# Fewest words a text needs to count as something two accounts can copy. Shorter texts ("good morning") are reused innocently.
MIN_WORDS = 5
# Fewest different items two accounts must share in one signal before they are linked.
MIN_SHARED = 2
# False discovery rate of the chance test (Benjamini-Hochberg).
ALPHA = 0.01
# A text of at least this many words links two accounts alone: a long text is not written twice by accident; shorter ones still need two.
LONG_WORDS = 10
# Smallest group of accounts that is a cluster.
MIN_SIZE = 3
# Most account-pair rows built; above it the most widely shared items are left out.
PAIR_BUDGET = 1_000_000_000
KINDS = ("text", "link", "repost", "reply")

# Column each kind reads; a kind is skipped when all of its columns are empty.
_NEEDS = {"text": ("text",), "link": ("text", "links"), "repost": ("repost_of",), "reply": ("parent_id",)}

_WORDS = r"""regexp_extract_all(
        regexp_replace(regexp_replace(lower(coalesce(text, '')), 'https?://\S+', ' ', 'g'), '@[\p{L}\p{N}_]+', ' ', 'g'),
        '[\p{L}\p{N}_]+')"""

# Same link whatever the scheme, `www.`, tracking parameters, fragment or trailing slash; path and query keep their case.
_LINK_KEY = r"""regexp_replace(lower(host), '^www\.', '') || regexp_replace(path, '/$', '') || case when q = '' then '' else '?' || q end"""

_ITEMS_SQL = r"""
create or replace table item as
with c as (select comment_id, username, timestamp as ts, text, links, parent_id, repost_of from comments),
t as (select *, __WORDS__ as words
      from c where repost_of is null),
raw as (
  select username, 'repost' as kind, hash(repost_of) as key, repost_of as value, ts, null::BIGINT as n_words
    from c where repost_of is not null
  union all
  select username, 'text', hash(array_to_string(words, ' ')), text, ts, len(words) from t where len(words) >= __MIN_WORDS__
  union all
  select username, 'link', hash(__LINK_KEY__), url, ts, null
    from (select username, ts, url,
                 regexp_extract(a, '^[^/?]*') as host, regexp_extract(a, '^[^/?]*([^?]*)', 1) as path,
                 -- query without tracking parameters; the '&' in front makes every parameter start the same way
                 regexp_replace(regexp_replace('&' || regexp_extract(a, '\?(.*)$', 1),
                                '&(utm_[^&=]*(=[^&]*)?|(fbclid|gclid)=[^&]*)', '', 'g'), '^&', '') as q
          from (select username, ts, url, regexp_replace(regexp_replace(url, '(?i)^https?://', ''), '#.*$', '') as a
                from (select username, ts, rtrim(unnest(regexp_extract_all(coalesce(text, '') || ' ' || coalesce(links, ''), '(?i)https?://\S+')), '.,)') as url
                      from c where repost_of is null)))
  union all
  select username, 'reply', hash(parent_id), parent_id, ts, null from c where parent_id is not null and repost_of is null)
select username, kind, key, first(value order by ts nulls last, value) as value, min(ts) as first_seen, max(ts) as last_seen,
       max(n_words) as words
from raw group by username, kind, key
"""

# Distinct normalised texts, for the optional similar-text signal.
_TEXT_NORM_SQL = r"""
create or replace table text_norm as
select distinct hash(norm) as key, norm from (
  select array_to_string(words, ' ') as norm, len(words) as n
  from (select __WORDS__ as words from comments where repost_of is null))
where n >= __MIN_WORDS__
"""


def _skipped(con):
    """Kinds whose input columns are entirely empty, with the reason."""
    filled = {}
    for column in ("text", "links", "repost_of", "parent_id"):
        filled[column] = con.execute(f"select count({column}) from comments").fetchall()[0][0] > 0
    out = {}
    for kind, columns in _NEEDS.items():
        if not any(filled[c] for c in columns):
            out[kind] = "column " + " and ".join(columns) + " is missing or empty" if len(columns) == 1 else \
                "columns " + " and ".join(columns) + " are both missing or empty"
    return out


def _max_sharers(con, pair_budget):
    """Largest number of accounts sharing one item whose pairs still fit in the budget (cheapest items first)."""
    rows = con.execute(
        "select df, count(*) * (df * (df - 1) // 2) from df where df >= 2 group by df order by df").fetchall()
    total, best = 0, 1
    for df, cost in rows:
        total += cost
        if total > pair_budget:
            break
        best = df
    return best


def _similar_rate(con):
    """N and S of `similar_text` over all of each account's texts, not only those with a near-duplicate.

    Counting only grouped texts lets a swarm whose copies are the only near-duplicates set its own chance rate.
    A text without a group is one unit of its own; S counts only pairs of units in the same group.
    """
    con.execute("""
        create or replace temp table similar_unit as
        select distinct i.username, coalesce(g.gkey, i.key) as key, g.gkey is not null as grouped
        from item i left join text_group g using (key) where i.kind = 'text'""")
    con.execute("delete from n where kind = 'similar_text'")
    con.execute("insert into n select username, 'similar_text', count(*) from similar_unit group by username")
    con.execute("delete from s where kind = 'similar_text'")
    con.execute("""
        insert into s select 'similar_text', sum(df::double * (df - 1) * grouped::int) / nullif(sum(df)::double * (sum(df) - 1), 0)
        from (select key, count(*) as df, bool_or(grouped) as grouped from similar_unit group by key)""")


def _clusters(links, min_size):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        parent[find(a)] = find(b)
    groups = {}
    for x in list(parent):
        groups.setdefault(find(x), []).append(x)
    return [sorted(g) for g in groups.values() if len(g) >= min_size]


def detect(con, *, min_shared=MIN_SHARED, alpha=ALPHA, min_size=MIN_SIZE, pair_budget=PAIR_BUDGET, similar_text=False,
           long_words=LONG_WORDS, similar_model=None):
    warnings = []
    skipped = _skipped(con)
    fill = lambda sql: sql.replace("__WORDS__", _WORDS).replace("__LINK_KEY__", _LINK_KEY).replace("__MIN_WORDS__", str(int(MIN_WORDS)))
    con.execute(fill(_ITEMS_SQL))
    if similar_text:
        if "text" in skipped:
            skipped["similar_text"] = skipped["text"]
        else:
            con.execute(fill(_TEXT_NORM_SQL))
            reason, similar_warnings = similar.add_items(con, model=similar_model)
            warnings += similar_warnings
            if reason:
                skipped["similar_text"] = reason
                warnings.append(f"similar_text skipped: {reason}")
    if con.execute("select count(*) from item").fetchall()[0][0] == 0:
        raise InputError("nothing to compare: needs comments with a text of at least "
                         f"{MIN_WORDS} words, links, repost_of or parent_id (columns text, links, repost_of, parent_id)")

    con.execute("create or replace table df as select kind, key, count(*) as df from item group by kind, key")
    con.execute("create or replace table n as select username, kind, count(*) as n from item group by username, kind")
    # chance that two different posts of one kind are the same item (unbiased: a post never matches itself)
    con.execute("create or replace table s as select kind, sum(df::double * (df - 1)) / nullif(sum(df)::double * (sum(df) - 1), 0) as s "
                "from df group by kind")
    if similar_text and con.execute("select count(*) from df where kind = 'similar_text'").fetchall()[0][0]:
        _similar_rate(con)

    max_sharers = _max_sharers(con, pair_budget)
    left_out = con.execute("select count(*) from df where df > ?", [max_sharers]).fetchall()[0][0]
    if left_out:
        warnings.append(f"pair budget {pair_budget:,} exceeded: left out {left_out:,} items shared by more than "
                        f"{max_sharers} accounts; they say least about coordination")

    con.execute("""
        create or replace table pair as
        with shared as (select i.username, i.kind, i.key, i.words from item i join df d using (kind, key)
                        where d.df between 2 and ?),
        p as (select a.username as u1, b.username as u2, a.kind, count(*) as c, count(*) filter (where a.words >= ?) as long
              from shared a join shared b on a.kind = b.kind and a.key = b.key and a.username < b.username
              group by all),
        e as (select p.*, n1.n * n2.n * s.s as expected
              from p join n n1 on n1.username = p.u1 and n1.kind = p.kind
                     join n n2 on n2.username = p.u2 and n2.kind = p.kind
                     join s on s.kind = p.kind)
        select u1, u2, kind, c, long,
               case when expected < c
                    then c * ln(expected) - expected - lgamma(c + 1) - ln(1 - expected / (c + 1))
                    else 0 end as logp
        from e""", [max_sharers, long_words or None])
    m = con.execute("select count(*) from pair").fetchall()[0][0]
    cut = None
    if m:
        cut = con.execute("""
            select max(logp) from (select logp, row_number() over (order by logp) as k from pair where logp < 0)
            where logp <= ln(?) + ln(k) - ln(?)""", [alpha, m]).fetchall()[0][0]
    con.execute("create or replace table link (u1 VARCHAR, u2 VARCHAR, kind VARCHAR, shared BIGINT)")
    if cut is not None:
        con.execute("insert into link select u1, u2, kind, c from pair where (c >= ? or long >= 1) and logp <= ?", [min_shared, cut])

    groups = _clusters(con.execute("select u1, u2 from link").fetchall(), min_size)
    con.execute("create or replace table member (username VARCHAR, cluster VARCHAR, copied_share DOUBLE)")
    con.execute("create or replace table cluster (cluster VARCHAR, size BIGINT, confidence DOUBLE)")
    if groups:
        ids = [hashlib.sha1(",".join(g).encode()).hexdigest()[:10] for g in groups]
        con.execute("create or replace temp table member_cluster as "
                    "select unnest(?::VARCHAR[]) as username, unnest(?::VARCHAR[]) as cluster",
                    [[u for g in groups for u in g], [i for g, i in zip(groups, ids) for _ in g]])
        con.execute("""
            insert into member
            with mi as (select mc.cluster, i.username, i.kind, i.key from item i join member_cluster mc using (username)),
            cnt as (select cluster, kind, key, count(*) as k from mi group by all)
            select mi.username, mi.cluster, avg((cnt.k > 1)::int) from mi join cnt using (cluster, kind, key)
            group by mi.cluster, mi.username""")
        con.execute("insert into cluster select cluster, count(*), round(avg(copied_share), 9) from member group by cluster")

    signals = {}
    for kind in KINDS + (("similar_text",) if similar_text else ()):
        if kind in skipped:
            signals[kind] = {"status": "skipped", "reason": skipped[kind], "items": 0, "links": 0}
            continue
        signals[kind] = {
            "status": "used", "reason": None,
            "items": con.execute("select count(*) from item where kind = ?", [kind]).fetchall()[0][0],
            "links": con.execute("select count(*) from link where kind = ?", [kind]).fetchall()[0][0]}
    return signals, warnings
