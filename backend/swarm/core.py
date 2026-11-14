import os
from datetime import timedelta

from . import detect as d
from .evaluate import evaluate
from .load import InputError, close, connect, load

MIN_CONFIDENCE = 0.2
# Caps so one huge cluster cannot make the result file unusable; edge_count stays the true number.
MAX_EDGES = 500
MAX_ITEMS = 20

_TS = "strftime({}, '%Y-%m-%dT%H:%M:%SZ')"


def _created_within_30_days(dates):
    dates = sorted(dates)
    if not dates:
        return None
    best, lo = 0, 0
    for hi, t in enumerate(dates):
        while t - dates[lo] > timedelta(days=30):
            lo += 1
        best = max(best, hi - lo + 1)
    return {"accounts": best, "of": len(dates)}


def _clusters(con, min_confidence):
    ts = _TS.format
    con.execute("create or replace temp table kept as select cluster, size, confidence from cluster where confidence >= ?",
                [min_confidence])
    out = {c: {"id": c, "size": size, "confidence": round(conf, 3), "accounts": [], "edge_count": 0, "edges": [],
               "top_items": [], "first_seen": None, "last_seen": None, "created_within_30_days": None}
           for c, size, conf in con.execute("select * from kept").fetchall()}

    for c, user, share in con.execute(
            "select cluster, username, copied_share from member where cluster in (select cluster from kept) "
            "order by cluster, copied_share desc, username").fetchall():
        out[c]["accounts"].append({"username": user, "copied_share": round(share, 3)})

    for c, a, b, kind, shared, total in _edges(con):
        out[c]["edge_count"] = total
        out[c]["edges"].append({"source": a, "target": b, "kind": kind, "shared": shared})

    con.execute("""
        create or replace temp table shared_item as
        select m.cluster, i.kind, i.key, count(*) as accounts,
               first(i.value order by i.first_seen nulls last, i.value) as value,
               min(i.first_seen) as first_seen, max(i.last_seen) as last_seen
        from item i join member m using (username)
        where m.cluster in (select cluster from kept)
        group by m.cluster, i.kind, i.key
        having count(*) >= 2""")
    for c, first, last in con.execute(
            f"select cluster, {ts('min(first_seen)')}, {ts('max(last_seen)')} from shared_item group by cluster").fetchall():
        out[c]["first_seen"], out[c]["last_seen"] = first, last
    for c, kind, value, accounts, first, last in con.execute(f"""
            select cluster, kind, value, accounts, {ts('first_seen')}, {ts('last_seen')} from (
              select *, row_number() over (partition by cluster order by accounts desc, first_seen, kind, value) as rn
              from shared_item)
            where rn <= {MAX_ITEMS} order by cluster, rn""").fetchall():
        out[c]["top_items"].append({"kind": kind, "value": value, "accounts": accounts, "first_seen": first, "last_seen": last})

    dates = {}
    for c, created in con.execute(
            "select m.cluster, p.created_at from member m join profiles p using (username) "
            "where p.created_at is not null and m.cluster in (select cluster from kept)").fetchall():
        dates.setdefault(c, []).append(created)
    for c, found in dates.items():
        out[c]["created_within_30_days"] = _created_within_30_days(found)

    return sorted(out.values(), key=lambda c: (-c["confidence"], -c["size"], c["id"]))


def _edges(con):
    return con.execute(f"""
        select cluster, u1, u2, kind, shared, total from (
          select m.cluster, l.u1, l.u2, l.kind, l.shared,
                 count(*) over (partition by m.cluster) as total,
                 row_number() over (partition by m.cluster order by l.shared desc, l.u1, l.u2, l.kind) as rn
          from link l join member m on m.username = l.u1
          where m.cluster in (select cluster from kept))
        where rn <= {MAX_EDGES}
        order by cluster, rn""").fetchall()


def _ignore(con, path):
    """Delete the accounts named in the file (one per line, `#` comments) from the tables. Returns the warnings and the count."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = [line.strip() for line in f]
    except (OSError, UnicodeDecodeError):
        raise InputError(f"cannot read the ignore list {path}") from None
    names = sorted({line for line in lines if line and not line.startswith("#")})
    listed = "list_contains(?::VARCHAR[], username)"
    accounts, rows = con.execute(f"select count(distinct username), count(*) from comments where {listed}", [names]).fetchall()[0]
    for table in ("comments", "profiles"):
        con.execute(f"delete from {table} where {listed}", [names])
    if not con.execute("select count(*) from comments").fetchall()[0][0]:
        raise InputError("the ignore list leaves no comments to analyse")
    warnings = [f"ignore list: left out {accounts} accounts ({rows} comments)"]
    if len(names) > accounts:
        warnings.append(f"ignore list: {len(names) - accounts} names match no account")
    return warnings, accounts


def analyze(comments_path, profiles_path=None, *, min_confidence=MIN_CONFIDENCE, min_shared=d.MIN_SHARED,
            alpha=d.ALPHA, min_size=d.MIN_SIZE, pair_budget=d.PAIR_BUDGET, similar_text=False, ignore_path=None):
    con = connect()
    try:
        warnings = load(con, comments_path, profiles_path)
        if ignore_path is not None:
            ignore_warnings, ignored = _ignore(con, ignore_path)
            warnings += ignore_warnings
        signals, detect_warnings = d.detect(con, min_shared=min_shared, alpha=alpha, min_size=min_size,
                                            pair_budget=pair_budget, similar_text=similar_text)
        comments, accounts, synthetic = con.execute(
            "select count(*), count(distinct username), coalesce(bool_or(synthetic), false) from comments").fetchall()[0]
        return {
            "source": {"comments_file": os.path.basename(comments_path),
                       "profiles_file": os.path.basename(profiles_path) if profiles_path else None,
                       "comments": comments, "accounts": accounts, "synthetic": bool(synthetic)},
            "parameters": {"min_words": d.MIN_WORDS, "min_shared": min_shared, "alpha": alpha, "min_size": min_size,
                           "min_confidence": min_confidence, **({"similar_text": True} if similar_text else {}),
                           **({"ignored_accounts": ignored} if ignore_path is not None else {})},
            "signals": signals,
            "warnings": warnings + detect_warnings,
            "clusters": _clusters(con, min_confidence),
            "metrics": evaluate(con, min_confidence),
        }
    finally:
        close(con)
