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
# Two accounts created within this many days of each other count one more shared item, but only on top of shared
# content: accounts made in one batch is the mark of a swarm that writes short, varied comments (Test R). The same
# window as the `created_within_30_days` evidence; its chance rate is measured from the data like every other item's.
# The 30 days were not tuned, but the test's form was: adding the creation to every dated pair came first and weakened
# strong pairs on a labelled run, so it is now tried both ways and the stronger counted (PLAN.md, Results).
CREATED_DAYS = 30
# Smallest group of accounts that is a cluster.
MIN_SIZE = 3
# Most account-pair rows built; above it the most widely shared items are left out.
PAIR_BUDGET = 1_000_000_000
KINDS = ("text", "link", "repost", "reply")
# Most sharers an item counts with in the chance rate. Chosen 14.11 night with labels visible: 3, 5 and 10 tried on
# Test A and Cresci; 3 and 5 made the synthetic look-alikes (a viral post, breaking news, fans) into clusters, so 10 is
# the smallest that keeps them apart. To be checked on held-out data. None: no cap.
RATE_CAP = 10

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


def _logp(c, expected):
    """SQL for the log of an upper bound on P(X >= c) for X ~ Poisson(expected); 0 when c is not above what is expected."""
    return (f"(case when {expected} < {c} then {c} * ln({expected}) - {expected} - lgamma({c} + 1) "
            f"- ln(1 - {expected} / ({c} + 1)) else 0 end)")


def _born(con, days):
    """Table `born` (accounts with content and a creation time) and the chance that two of them are within `days`."""
    con.execute("""
        create or replace temp table born as
        select username, max(created_at) as created_at from profiles
        where created_at is not null and username in (select distinct username from item) group by username""")
    accounts, near = con.execute(f"""
        select count(*), coalesce(sum(w - 1), 0) from (
          select count(*) over (order by created_at range between interval {int(days)} days preceding
                                and interval {int(days)} days following) as w from born)""").fetchall()[0]
    return accounts, (near / (accounts * (accounts - 1)) if accounts >= 2 else 0.0)


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
           long_words=LONG_WORDS, similar_model=None, created_days=CREATED_DAYS, rate_cap=RATE_CAP):
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

    # An account seen in one thread only (no history fetched, or none exists) replies to that thread's posts because it
    # is in the thread: replying to the same posts as others is no evidence for it. Its copied text, links and reposts
    # still count, so a review page's copy-paste swarm is still found (handoff 6e, R7).
    con.execute("""
        create or replace table thread_only as select username from comments group by username
        having count(thread_id) = count(*) and count(distinct thread_id) = 1""")
    con.execute("delete from item where kind = 'reply' and username in (select username from thread_only)")

    con.execute("create or replace table df as select kind, key, count(*) as df from item group by kind, key")
    con.execute("create or replace table n as select username, kind, count(*) as n from item group by username, kind")
    # chance that two different posts of one kind are the same item (unbiased: a post never matches itself)
    # An item counts toward the chance rate as if at most `rate_cap` accounts shared it: a large botnet's own copies
    # otherwise set the rate (humans share 11-16 times less often than the uncapped rate predicts, Test A).
    # Not for replies: many accounts answering one popular post is what people do (a thread's story and top comment,
    # handoff 6e R7); capped, every pair of commenters who answered both would look coordinated.
    con.execute("create or replace table s as select kind, sum(c::double * (c - 1)) / nullif(sum(df)::double * (sum(df) - 1), 0) as s "
                "from (select kind, df, case when kind = 'reply' then df else least(df, ?) end as c from df) group by kind",
                [rate_cap])
    if similar_text and con.execute("select count(*) from df where kind = 'similar_text'").fetchall()[0][0]:
        _similar_rate(con)

    if created_days:
        born_accounts, born_rate = _born(con, created_days)
    else:
        con.execute("create or replace temp table born (username VARCHAR, created_at TIMESTAMP)")
        born_accounts, born_rate = 0, 0.0

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
        b as (select p.*,
                     coalesce(abs(epoch(b1.created_at) - epoch(b2.created_at)) <= ? * 86400, false) as together
              from p left join born b1 on b1.username = p.u1 left join born b2 on b2.username = p.u2),
        e as (select b.u1, b.u2, b.kind, b.c, b.long, b.together, n1.n * n2.n * s.s as expected
              from b join n n1 on n1.username = b.u1 and n1.kind = b.kind
                     join n n2 on n2.username = b.u2 and n2.kind = b.kind
                     join s on s.kind = b.kind),
        -- Tested twice when the two were created together: on the content alone, and with the creation as one more item
        -- whose chance is added to what is expected. The stronger counts. Only the second test carries a Bonferroni
        -- factor 2 (ln 2), so for pairs created together the false-positive rate can reach 1.5 times the nominal one.
        -- Adding a common event to a rare one must never weaken it (bots created in bursts make that chance large).
        t as (select *, __LOGP__(c, expected) as alone,
                     case when together then __LOGP__(c + 1, expected + ?) + ln(2) end as with_born from e)
        select u1, u2, kind, case when with_born < alone then c + 1 else c end as c, long,
               together and with_born < alone as together, least(alone, coalesce(with_born, alone)) as logp
        from t""".replace("__LOGP__(c + 1, expected + ?)", _logp("(c + 1)", f"(expected + {float(born_rate)!r})"))
                 .replace("__LOGP__(c, expected)", _logp("c", "expected")),
                [max_sharers, long_words or None, created_days])
    m = con.execute("select count(*) from pair").fetchall()[0][0]
    cut = None
    if m:
        cut = con.execute("""
            select max(logp) from (select logp, row_number() over (order by logp) as k from pair where logp < 0)
            where logp <= ln(?) + ln(k) - ln(?)""", [alpha, m]).fetchall()[0][0]
    con.execute("create or replace table link (u1 VARCHAR, u2 VARCHAR, kind VARCHAR, shared BIGINT, created_together BOOLEAN)")
    if cut is not None:
        con.execute("insert into link select u1, u2, kind, c, together from pair where (c >= ? or long >= 1) and logp <= ?",
                    [min_shared, cut])

    groups = _clusters(con.execute("select u1, u2 from link").fetchall(), min_size)
    con.execute("create or replace table member (username VARCHAR, cluster VARCHAR, copied_share DOUBLE)")
    con.execute("create or replace table cluster (cluster VARCHAR, size BIGINT, confidence DOUBLE)")
    if groups:
        ids = [hashlib.sha1(",".join(g).encode()).hexdigest()[:10] for g in groups]
        con.execute("create or replace temp table member_cluster as "
                    "select unnest(?::VARCHAR[]) as username, unnest(?::VARCHAR[]) as cluster",
                    [[u for g in groups for u in g], [i for g, i in zip(groups, ids) for _ in g]])
        # Copied share per kind, weighted by how many of the cluster's links that kind carries: a botnet linked by reposts
        # that also writes text nobody copies (Fox8-23: 0.24 over all kinds, 0.60 over reposts) is not diluted by it, even
        # when a few member pairs are also linked by text. Kinds a member never posts in leave its average.
        con.execute("""
            insert into member
            with lw as (select a.cluster, l.kind, count(*)::double as w from link l
                        join member_cluster a on a.username = l.u1 join member_cluster b on b.username = l.u2
                        where a.cluster = b.cluster group by all),
            mi as (select mc.cluster, i.username, i.kind, i.key from item i join member_cluster mc using (username)
                   join lw on lw.cluster = mc.cluster and lw.kind = i.kind),
            cnt as (select cluster, kind, key, count(*) as k from mi group by all),
            per as (select mi.cluster, mi.username, mi.kind, avg((cnt.k > 1)::int) as s from mi join cnt using (cluster, kind, key)
                    group by all),
            share as (select per.username, per.cluster, sum(per.s * lw.w) / sum(lw.w) as s from per join lw using (cluster, kind)
                      group by all)
            select mc.username, mc.cluster, coalesce(share.s, 0) from member_cluster mc left join share using (username, cluster)""")
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
    if not created_days or born_accounts < 2:
        signals["created_together"] = {"status": "skipped", "items": born_accounts, "links": 0,
                                       "reason": "off" if not created_days else "fewer than 2 accounts with created_at in the profiles"}
    else:
        signals["created_together"] = {"status": "used", "reason": None, "items": born_accounts,
                                       "links": con.execute("select count(*) from link where created_together").fetchall()[0][0]}
    return signals, warnings
