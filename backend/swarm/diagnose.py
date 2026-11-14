"""Why a result looks the way it does, above all why it found nothing (handoff 6, R5). Aggregates only; never changes
which clusters are listed or their confidence."""
import math

WINDOW_DAYS = 7      # "near the thread": the same ±7 days the collector fetches histories for
THIN_SHARE = 0.3     # reason thin_histories when at least this share of accounts was seen in one thread only
VALUE_CHARS = 200


NEAR_SHARE = 0.2     # reason histories_far when under this share of the other posts falls near the main thread


def _n(count, one, many=None):
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _p(logp):
    return None if logp is None else float(f"{math.exp(logp):.3g}")


def _main_thread(con):
    """The thread with most comments, and how much of everything else falls near it in time."""
    row = con.execute("""
        select thread_id, count(*), count(distinct username), min(timestamp), max(timestamp) from comments
        where thread_id is not null group by thread_id order by count(*) desc, thread_id limit 1""").fetchall()
    if not row:
        return None
    tid, comments, accounts, first, last = row[0]
    other, near = con.execute(f"""
        select count(*), count(*) filter (where timestamp between ?::TIMESTAMP - interval {WINDOW_DAYS} days
                                                        and ?::TIMESTAMP + interval {WINDOW_DAYS} days)
        from comments where thread_id is distinct from ? and username in
             (select distinct username from comments where thread_id = ?)""", [first, last, tid, tid]).fetchall()[0]
    return {"thread_id": tid, "comments": comments, "accounts": accounts,
            "first_seen": first and first.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_seen": last and last.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "other_comments": other, "other_near_thread": round(near / other, 3) if other and first else None}


def diagnostics(con, *, min_shared, min_size, min_confidence, listed):
    accounts = con.execute("select count(distinct username) from comments").fetchall()[0][0]
    thread_only = con.execute("select count(*) from thread_only").fetchall()[0][0]
    threads = con.execute("select count(distinct thread_id) from comments").fetchall()[0][0]
    cut = con.execute("select cut from chance_cut").fetchall()[0][0]
    by_kind = {}
    for kind, sharing, enough, best in con.execute(
            "select kind, count(*), count(*) filter (where c >= ? or long >= 1), "
            "min(logp) filter (where c >= ? or long >= 1) from pair group by kind order by kind",
            [min_shared, min_shared]).fetchall():
        by_kind[kind] = {"pairs_sharing": sharing, "pairs_sharing_enough": enough, "pairs_linked": 0,
                         "closest_p": _p(best)}
    for kind, n in con.execute("select kind, count(*) from link group by kind").fetchall():
        by_kind.setdefault(kind, {"pairs_sharing": 0, "pairs_sharing_enough": 0, "pairs_linked": 0, "closest_p": None})
        by_kind[kind]["pairs_linked"] = n
    roots = "select distinct thread_id from comments where thread_id is not null"
    widest = [{"kind": k, "accounts": a, "value": (v or "")[:VALUE_CHARS], "opening_post": bool(o)}
              for k, a, v, o in con.execute(
                  f"select kind, accounts, value, kind = 'reply' and value in ({roots}) from widest "
                  "order by accounts desc, kind, key").fetchall()]
    groups, below = con.execute("select count(*), count(*) filter (where confidence < ?) from cluster",
                                [min_confidence]).fetchall()[0]
    enough = sum(k["pairs_sharing_enough"] for k in by_kind.values())
    linked = sum(k["pairs_linked"] for k in by_kind.values())

    reasons = []
    if accounts and thread_only / accounts >= THIN_SHARE:
        reasons.append({"code": "thin_histories", "text":
                        f"{thread_only} of {accounts} accounts were seen in this one thread only (no other posts), so "
                        "replying to the same posts is not counted against them and little else can link them."})
    if not enough:
        reasons.append({"code": "nothing_shared_enough", "text":
                        f"No two accounts shared {min_shared} or more items (the same text, link, repost or replied-to "
                        "post): there is nothing to test."})
    elif enough > linked:
        top = widest[0] if widest else None
        what = ""
        if top and top["opening_post"]:
            what = f" The most widely shared item: {top['accounts']} accounts replied to the thread's opening post."
        elif top:
            what = f" The most widely shared item was a {top['kind']} shared by {top['accounts']} accounts."
        reasons.append({"code": "explained_by_chance", "text":
                        f"{enough - linked} of {_n(enough, 'account pair')} that shared {min_shared} or more items "
                        f"shared no more than chance gives accounts this active.{what}"})
    if linked and not groups:
        reasons.append({"code": "no_group", "text":
                        f"{_n(linked, 'account pair')} shared more than chance, but they form no group of {min_size} or more "
                        "accounts."})
    if below and not listed:
        reasons.append({"code": "below_cut", "text":
                        f"{_n(below, 'group')} found with a confidence under the cut {min_confidence}: their members "
                        "copy only a small part of what they post."})
    main = _main_thread(con) if threads else None
    if main and main["other_comments"] and main["other_near_thread"] is not None and main["other_near_thread"] < NEAR_SHARE:
        reasons.append({"code": "histories_far", "text":
                        f"Only {round(100 * main['other_near_thread'])}% of these accounts' other posts are within "
                        f"{WINDOW_DAYS} days of the thread: they show what the accounts do at another time, not around it."})
    return {"accounts": accounts, "thread_only_accounts": thread_only, "threads": threads,
            "chance_cut_p": _p(cut), "groups_found": groups, "groups_below_cut": below,
            "by_kind": by_kind, "widest_items": widest, "main_thread": main,
            "reasons": reasons}
