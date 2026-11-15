"""Discourse forums (thousands of communities run it): a topic's every post and each poster's posts from around the
topic's date, from the forum's public JSON (the same URL with .json; no login, no credits).

Bundle pages: the topic JSON with every post in post_stream.posts (the first 20 come with the topic, the rest from
/t/ID/posts.json), and per poster {"user_actions": [...]} (their topics and replies, filter 4,5). swarm.convert
(sites.from_json) reads both. A link to any other site with /t/slug/123 is tried too and refused when it is not Discourse.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .around import FREE_PARTICIPANTS, most_active, when, window
from .contextdev import CollectError

TOPIC_URL = re.compile(r"^(https?://[^/]+(?:/[^/]+)*?)/t/(?:[^/?#]+/)?(\d+)(?:/\d+)?/?(?:[?#].*)?$", re.I)
BATCH = 20            # post ids per posts.json request
MAX_POSTS = 3000
PAGE = 30             # user_actions per page
MAX_PAGES = 5
MAX_PARTICIPANTS = FREE_PARTICIPANTS
DIRECT_WORKERS = 4    # forums limit anonymous requests per IP


def matches(url):
    return bool(TOPIC_URL.match(url))


def _history(client, base, username, limit, around):
    """Up to `limit` of one user's topics and replies nearest the topic's date (paging back), else the newest."""
    first, kept = [], []
    for page in range(MAX_PAGES if around else 1):
        url = f"{base}/user_actions.json?username={quote(username, safe='')}&filter=4,5&offset={page * PAGE}"
        got = client.direct_json(url)
        actions = [a for a in (got.get("user_actions") or []) if isinstance(a, dict)] if isinstance(got, dict) else []
        first = first or actions
        if not around or not actions:
            break
        times = [(when(a.get("created_at")), a) for a in actions]
        kept += [(t, a) for t, a in times if t and around[0] <= t <= around[1]]
        oldest = min((t for t, _ in times if t), default=None)
        if len(actions) < PAGE or (oldest and oldest < around[0]):
            break
    if not kept:
        return {"user_actions": first[:limit]}
    middle = around[0] + (around[1] - around[0]) / 2
    return {"user_actions": [a for _, a in sorted(kept, key=lambda ta: abs(ta[0] - middle))[:limit]]}


def collect(url, client, history, max_participants, on_progress):
    base, topic_id = TOPIC_URL.match(url).groups()
    try:
        topic = client.direct_json(f"{base}/t/{topic_id}.json")
    except CollectError:
        topic = None
    stream = (topic or {}).get("post_stream") if isinstance(topic, dict) else None
    if not isinstance(stream, dict) or not isinstance(stream.get("posts"), list):
        raise CollectError("That topic was not found, or the site is not a public Discourse forum.")
    posts = [p for p in stream["posts"] if isinstance(p, dict)]
    have = {p.get("id") for p in posts}
    missing = [i for i in (stream.get("stream") or []) if i not in have][:max(0, MAX_POSTS - len(posts))]
    for i in range(0, len(missing), BATCH):
        ids = "&".join(f"post_ids[]={int(x)}" for x in missing[i:i + BATCH])
        try:
            more = client.direct_json(f"{base}/t/{topic_id}/posts.json?{ids}")
            posts += [p for p in ((more.get("post_stream") or {}).get("posts") or []) if isinstance(p, dict)]
        except Exception:            # a failed batch leaves those posts out; the coverage note says how many
            pass
    posts.sort(key=lambda p: p.get("post_number") or 0)
    topic = dict(topic, post_stream=dict(stream, posts=posts))

    names = most_active([p["username"] for p in posts if p.get("username")])
    fetch = names[:max_participants]
    around = window(when(posts[0].get("created_at") if posts else topic.get("created_at")))
    limit = max(1, int(history))
    pages = [{"url": f"{base}/t/{topic_id}.json", "role": "thread", "json": topic}]

    def one(name):
        try:
            return name, _history(client, base, name, limit, around)
        except Exception:            # one account failing must not stop the rest
            return name, None

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=max(client.workers, DIRECT_WORKERS)) as pool:
        for n, (name, got) in enumerate(pool.map(one, fetch), 1):
            if got is None:
                failed += 1
            else:
                ok += 1
                pages.append({"url": f"{base}/user_actions.json?username={quote(name, safe='')}", "role": "profile", "json": got})
            if on_progress:
                on_progress(n, len(fetch))

    expected = int(topic.get("posts_count") or len(stream.get("stream") or []) or 0)
    notes = []
    if expected > len(posts):
        notes.append(f"thread: the topic counts {expected} posts, {len(posts)} could be read")
    if len(names) > len(fetch):
        notes.append(f"thread: {len(names)} posters, posts were fetched for the {len(fetch)} most active; "
                     "the others are judged on their posts in this topic only")
    if failed:
        notes.append(f"thread: the posts of {failed} posters could not be fetched")
    host = re.sub(r"^https?://", "", base)
    return {
        "pages": pages, "notes": notes, "found": max(0, len(posts) - 1), "expected": max(0, expected - 1) or None,
        "thread": {"platform": f"Discourse ({host})", "label": f"Discourse topic {host} {topic_id}", "url": url,
                   "post_id": str(topic_id), "title": topic.get("title") or "", "author": posts[0].get("username") if posts else None,
                   "commenters": len(names), "commenters_fetched": len(fetch), "history_per_commenter": limit,
                   "histories_ok": ok, "histories_failed": failed},
    }
