"""Reddit: the rendered thread page (Context.dev, what a browser shows before "load more"), then each commenter's
newest comments with the `reddit-user` prebuilt parser. Needs the Context.dev key.

The page goes into the bundle as `html`, each history as `parsed` exactly as Context.dev returned it;
swarm.convert reads both, so the comments of the page are parsed only there.
"""
import html as html_lib
import re
from concurrent.futures import ThreadPoolExecutor

from ..convert import ConvertError, convert
from .contextdev import CollectError

THREAD_URL = re.compile(r"^https?://(?:[\w-]+\.)?reddit\.com/(?:r/[^/]+/)?comments/([A-Za-z0-9]+)", re.I)
USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,20}$")      # Reddit's own rule for usernames
SKIP = {"[deleted]", "automoderator", "deleted"}
POST_TAG = re.compile(r"<shreddit-post\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")
ATTR = re.compile(r"([\w-]+)=(?:\"([^\"]*)\"|'([^']*)')")


def matches(url):
    return bool(THREAD_URL.match(url))


def _post(page):
    """id, title, subreddit and Reddit's own comment count from the <shreddit-post> tag (attributes only)."""
    m = POST_TAG.search(page)
    a = {k: html_lib.unescape(v or w) for k, v, w in ATTR.findall(m.group(1))} if m else {}
    count = a.get("comment-count") or ""
    return {"id": re.sub(r"^t3_", "", a.get("id") or ""), "title": a.get("post-title") or "",
            "subreddit": a.get("subreddit-prefixed-name") or "", "expected": int(count) if count.isdigit() else None}


def collect(url, client, history, max_participants, on_progress):
    page = client.fetch_html(url, must_contain="<shreddit-comment ")
    if not page:
        raise CollectError("Reddit did not show the comments this time (it sometimes answers with a bot check). "
                           "Try again in a minute, or save the thread page and convert it with python -m swarm.convert.")
    post = _post(page)
    try:
        rows, _, _ = convert({"url": url, "site": "reddit", "pages": [{"url": url, "role": "thread", "html": page}]})
    except ConvertError:
        raise CollectError("No comments found on that Reddit page.") from None
    rows = [r for r in rows if r["comment_id"] != post["id"]]      # the converter also returns the post itself
    people = list(dict.fromkeys(r["username"] for r in rows))
    names = [n for n in people if USERNAME.match(n) and n.lower() not in SKIP][:max_participants]
    pages = [{"url": url, "role": "thread", "html": page}]

    def one(name):
        return client.parse(f"https://www.reddit.com/user/{name}/comments/?sort=new", "reddit-user", limit=history)

    ok = failed = suspended = 0
    with ThreadPoolExecutor(max_workers=client.workers) as pool:
        for n, (name, parsed) in enumerate(zip(names, pool.map(one, names)), 1):
            if not parsed.get("success"):
                failed += 1
            else:
                if (parsed.get("data") or {}).get("comments") is None:
                    suspended += 1
                else:
                    ok += 1
                pages.append({"url": f"https://www.reddit.com/user/{name}", "role": "profile", "parsed": parsed})
            if on_progress:
                on_progress(n, len(names))

    notes = []
    if len(people) > len(names):
        notes.append(f"thread: {len(people)} commenters, recent comments were fetched for {len(names)} of them; "
                     "the others are judged on their posts in this thread only")
    if failed:
        notes.append(f"thread: the recent comments of {failed} commenters could not be fetched")
    return {
        "pages": pages, "notes": notes, "found": len(rows), "expected": post["expected"],   # convert warns "read N of M" itself
        "thread": {"platform": "Reddit", "label": f"Reddit thread {post['subreddit']} {post['id']}".replace("  ", " ").strip(),
                   "subreddit": post["subreddit"], "title": post["title"], "url": url, "post_id": post["id"],
                   "commenters": len(people), "commenters_fetched": len(names), "history_per_commenter": history,
                   "histories_ok": ok, "histories_failed": failed, "histories_suspended": suspended},
    }
