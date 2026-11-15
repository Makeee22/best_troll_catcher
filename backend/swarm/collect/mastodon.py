"""Mastodon and compatible servers (the fediverse): a post's whole thread and each participant's posts from around its
date, from the server's public API (no login, no credits). One module for every server: the link names the server.

Bundle pages: {"status": the post, "ancestors": [...], "descendants": [...]} (the post plus /context, unchanged), and
per participant {"statuses": [...]}, the posts kept from /accounts/ID/statuses. swarm.convert (sites.from_json) reads both.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .around import FREE_PARTICIPANTS, most_active, when, window
from .contextdev import CollectError

POST_URL = re.compile(r"^https?://([^/]+)/@[A-Za-z0-9_.@-]+/(\d+)/?(?:[?#].*)?$", re.I)
PAGE = 40           # statuses per request, the API's most
MAX_PAGES = 5
MAX_PARTICIPANTS = FREE_PARTICIPANTS
DIRECT_WORKERS = 8


def matches(url):
    return bool(POST_URL.match(url))


def _history(client, api, account_id, limit, around):
    """Up to `limit` statuses of one account nearest the thread's date (paging back MAX_PAGES), else its newest.
    shortcut: a remote account's statuses are those this server has seen, not its full history; fetch them from its
    own server when that matters."""
    first, kept, max_id = [], [], None
    for _ in range(MAX_PAGES if around else 1):
        url = f"{api}accounts/{account_id}/statuses?limit={PAGE if around else limit}" + (f"&max_id={max_id}" if max_id else "")
        page = client.direct_json(url, allow_list=True)
        page = [s for s in page if isinstance(s, dict)] if isinstance(page, list) else []
        first = first or page
        if not around or not page:
            break
        times = [(when(s.get("created_at")), s) for s in page]
        kept += [(t, s) for t, s in times if t and around[0] <= t <= around[1]]
        max_id = page[-1].get("id")
        oldest = min((t for t, _ in times if t), default=None)
        if not max_id or (oldest and oldest < around[0]):
            break
    if not kept:
        return {"statuses": first[:limit]}
    middle = around[0] + (around[1] - around[0]) / 2
    return {"statuses": [s for _, s in sorted(kept, key=lambda ts: abs(ts[0] - middle))[:limit]]}


def collect(url, client, history, max_participants, on_progress):
    host, status_id = POST_URL.match(url).groups()
    api = f"https://{host}/api/v1/"
    try:
        status = client.direct_json(f"{api}statuses/{status_id}")
        context = client.direct_json(f"{api}statuses/{status_id}/context")   # an object: ancestors, descendants
    except CollectError:
        raise CollectError(f"That post was not found on {host}, or the server is not Mastodon-compatible.") from None
    if not isinstance(status, dict) or not status.get("account") or not isinstance(context, dict):
        raise CollectError(f"That post was not found on {host}, or the server is not Mastodon-compatible.")
    posts = [s for s in (context.get("ancestors") or []) + [status] + (context.get("descendants") or []) if isinstance(s, dict)]
    accounts = {}
    for s in posts:
        a = s.get("account") or {}
        if a.get("id"):
            accounts.setdefault(a["id"], a)
    ids = most_active([(s.get("account") or {}).get("id") for s in posts if (s.get("account") or {}).get("id")])[:max_participants]
    pages = [{"url": f"{api}statuses/{status_id}/context", "role": "thread",
              "json": {"status": status, "ancestors": context.get("ancestors") or [], "descendants": context.get("descendants") or []}}]
    root = posts[0]
    around = window(when(root.get("created_at")))
    limit = max(1, int(history))

    def one(account_id):
        try:
            return account_id, _history(client, api, account_id, limit, around)
        except Exception:            # one account failing must not stop the rest
            return account_id, None

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=max(client.workers, DIRECT_WORKERS)) as pool:
        for n, (account_id, got) in enumerate(pool.map(one, ids), 1):
            if got is None:
                failed += 1
            else:
                ok += 1
                pages.append({"url": f"{api}accounts/{account_id}/statuses", "role": "profile", "json": got})
            if on_progress:
                on_progress(n, len(ids))

    found = len(context.get("descendants") or [])
    expected = sum(int(s.get("replies_count") or 0) for s in [status] + (context.get("descendants") or []))
    notes = []
    if expected > found:
        notes.append(f"thread: the posts count {expected} replies, {host} returned {found}; a server shows only the "
                     "replies it has received from other servers")
    if len(accounts) > len(ids):
        notes.append(f"thread: {len(accounts)} participants, posts were fetched for the {len(ids)} most active; "
                     "the others are judged on their posts in this thread only")
    if failed:
        notes.append(f"thread: the posts of {failed} participants could not be fetched")
    return {
        "pages": pages, "notes": notes, "found": found, "expected": expected or None,
        "thread": {"platform": f"Mastodon ({host})", "label": f"Mastodon thread {host} {status_id}", "url": url,
                   "post_id": str(root.get("id") or status_id), "title": "", "author": (root.get("account") or {}).get("acct"),
                   "commenters": len(accounts), "commenters_fetched": len(ids), "history_per_commenter": limit,
                   "histories_ok": ok, "histories_failed": failed},
    }
