"""Hacker News: the whole comment tree (Algolia items/ID) and each commenter's recent comments (Algolia search_by_date).

Public API, no key and no Context.dev credits. The responses go into the bundle unchanged as `json` pages.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .contextdev import CollectError

API = "https://hn.algolia.com/api/v1/"
SEARCH = "search_by_date"   # newest first; plain "search" ranks by relevance and missed the newest comment for 2 of 6 authors
ITEM_URL = re.compile(r"^https?://(?:www\.)?news\.ycombinator\.com/item\?(?:[^#]*&)?id=(\d+)(?:[&#].*)?$", re.I)


def matches(url):
    return bool(ITEM_URL.match(url))


def _walk(item):
    """(authors in order of first appearance, comments with an author, deleted ones); a loop, not recursion."""
    people, read, deleted, stack = {}, 0, 0, [item]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if node is not item:
            read += bool(node.get("author"))
            deleted += not node.get("author")
        if node.get("author"):
            people.setdefault(node["author"], None)
        stack.extend(reversed(node.get("children") or []))
    return list(people), read, deleted


def collect(url, client, history, max_participants, on_progress):
    item_id = ITEM_URL.match(url).group(1)
    item_url = f"{API}items/{item_id}"
    try:
        item = client.direct_json(item_url)
    except CollectError:
        raise CollectError("That Hacker News item was not found.") from None
    if not isinstance(item, dict) or not item.get("id"):
        raise CollectError("That Hacker News item was not found.")
    people, read, deleted = _walk(item)
    names = people[:max_participants]
    pages = [{"url": item_url, "role": "thread", "json": item}]

    def one(name):
        search = f"{API}{SEARCH}?tags=comment,author_{quote(name, safe='')}&hitsPerPage={int(history)}"
        try:
            return search, client.direct_json(search)
        except Exception:            # one account failing must not stop the rest
            return None

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=client.workers) as pool:
        for n, got in enumerate(pool.map(one, names), 1):
            if got is None:
                failed += 1
            else:
                ok += 1
                pages.append({"url": got[0], "role": "profile", "json": got[1]})
            if on_progress:
                on_progress(n, len(names))

    notes = []
    if deleted:
        notes.append(f"thread: {deleted} deleted or dead comments have no author or text and are left out")
    if len(people) > len(names):
        notes.append(f"thread: {len(people)} commenters, recent comments were fetched for the first {len(names)}; "
                     "the others are judged on their posts in this thread only")
    if failed:
        notes.append(f"thread: the recent comments of {failed} commenters could not be fetched")
    kind = item.get("type") or "item"
    return {
        "pages": pages, "notes": notes, "found": read, "expected": None,   # Algolia gives no total to check against
        "thread": {"platform": "Hacker News", "label": f"Hacker News {kind} {item_id}", "title": item.get("title"),
                   "author": item.get("author"), "url": url, "post_id": item_id, "comments_hidden": deleted,
                   "commenters": len(people), "commenters_fetched": len(names), "history_per_commenter": history,
                   "histories_ok": ok, "histories_failed": failed},
    }
