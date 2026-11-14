"""Bluesky: the whole thread, each participant's newest posts, and their profiles, from the public AppView API.

No login. Every request goes through the client's fetch_json (Context.dev, with a direct fallback), and the
responses go into the bundle unchanged as `json` pages; swarm.convert (sites.from_json) reads them.
Ported from frontend/api/bluesky.py, without the row conversion.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .contextdev import CollectError

API = "https://public.api.bsky.app/xrpc/"
POST_URL = re.compile(r"^(?:https?://)?(?:www\.)?bsky\.app/profile/([A-Za-z0-9.:_-]+)/post/([A-Za-z0-9]+)/?(?:[?#].*)?$", re.I)
MAX_HISTORY = 100         # getAuthorFeed gives at most 100 per call


def matches(url):
    return bool(POST_URL.match(url))


def _get(client, via, method, **params):
    pairs = [(k, x) for k, v in params.items() for x in (v if isinstance(v, list) else [v])]
    q = "&".join(f"{k}={quote(str(x), safe='')}" for k, x in pairs)   # a list repeats its parameter: actors=a&actors=b
    url = f"{API}{method}?{q}"
    data, how = client.fetch_json(url)
    via[how] = via.get(how, 0) + 1
    return url, data


def _name(author):
    handle = author.get("handle") or ""
    return handle if handle and handle != "handle.invalid" else author.get("did") or handle


def _uri(client, via, url):
    actor, rkey = POST_URL.match(url).groups()
    if actor.lower().startswith("did:"):
        did = actor
    else:
        try:
            did = _get(client, via, "com.atproto.identity.resolveHandle", handle=actor.lower())[1].get("did")
        except Exception:
            did = None
    if not did:
        raise CollectError(f"Bluesky does not know the account {actor}.")
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def _walk(data):
    """(root post, [root + every visible reply], number of replies that are blocked or deleted)."""
    root = data.get("thread") or {}
    if not root.get("post"):
        raise CollectError("The post was not found, or it is not public.")
    posts, hidden, seen = [root["post"]], 0, {root["post"]["uri"]}
    stack = [root]                   # a loop, not recursion: a reply chain can be 1000 deep
    while stack:
        node = stack.pop()
        for r in reversed(node.get("replies") or []):
            post = r.get("post")
            if not post or not post.get("uri") or not (post.get("author") or {}).get("did"):
                hidden += 1
            elif post["uri"] not in seen:
                seen.add(post["uri"])
                posts.append(post)
                stack.append(r)
    return root["post"], posts, hidden


def collect(url, client, history, max_participants, on_progress):
    via = {}
    uri = _uri(client, via, url)
    try:
        thread_url, data = _get(client, via, "app.bsky.feed.getPostThread", uri=uri, depth=1000, parentHeight=0)
    except RecursionError:
        raise CollectError("This thread is nested too deeply to read.") from None
    except Exception as e:
        raise CollectError(f"The post was not found, or it is not public. ({str(e)[:120]})") from None
    root, posts, hidden = _walk(data)

    people = {}
    for p in posts:
        people.setdefault(p["author"]["did"], p["author"])
    dids = list(people)[:max_participants]
    pages = [{"url": thread_url, "role": "thread", "json": data}]
    limit = max(1, min(int(history), MAX_HISTORY))

    def one(did):
        try:
            return _get(client, via, "app.bsky.feed.getAuthorFeed", actor=did, limit=limit, filter="posts_with_replies")
        except Exception:            # one account failing must not stop the rest
            return None

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=client.workers) as pool:
        for n, got in enumerate(pool.map(one, dids), 1):
            if got is None:
                failed += 1
            else:
                ok += 1
                pages.append({"url": got[0], "role": "profile", "json": got[1]})
            if on_progress:
                on_progress(n, len(dids))
    for i in range(0, len(dids), 25):      # getProfiles takes 25 accounts per call
        try:
            u, d = _get(client, via, "app.bsky.actor.getProfiles", actors=dids[i:i + 25])
            pages.append({"url": u, "role": "profile", "json": d})
        except Exception:
            pass

    found = len(posts) - 1
    expected = sum(p.get("replyCount") or 0 for p in posts)   # the root's own replyCount counts direct replies only
    notes = []
    if expected > found:
        notes.append(f"thread: Bluesky counts {expected} replies, {found} could be read; "
                     f"the other {expected - found} are deleted, hidden or blocked")
    if len(people) > len(dids):
        notes.append(f"thread: {len(people)} participants, recent posts were fetched for the first {len(dids)}; "
                     "the others are judged on their posts in this thread only")
    if failed:
        notes.append(f"thread: the recent posts of {failed} participants could not be fetched")
    rec = root.get("record") or {}
    return {
        "pages": pages, "notes": notes, "found": found, "expected": expected,
        "thread": {"platform": "Bluesky", "label": f"Bluesky thread {root['uri']}", "title": (rec.get("text") or "")[:140],
                   "author": _name(root["author"]), "url": url, "post_id": root["uri"],
                   "direct_replies_expected": root.get("replyCount"), "comments_hidden": hidden,
                   "commenters": len(people), "commenters_fetched": len(dids), "history_per_commenter": history,
                   "histories_ok": ok, "histories_failed": failed, "via": via},
    }
