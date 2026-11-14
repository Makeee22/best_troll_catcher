"""Collect a Bluesky discussion from a post link: the whole thread, each participant's recent posts, profiles.

Bluesky's AppView API is public and needs no login (https://public.api.bsky.app/xrpc/...). Every request
goes through Context.dev (ContextDev.fetch_json), with a direct request as fallback.
The row conversion here is interim: it moves to the backend's converter (docs/collect-interface.md).

    b = Bluesky(client)
    data = b.collect("https://bsky.app/profile/someone.bsky.social/post/3abc...", history=30, on_progress=print)
    data["comments"], data["profiles"], data["thread"] (with the coverage counts), data["via"]

Rows follow the core's standard format (docs/api.md "Input files"); reposts in the histories become rows
with repost_of, which feeds the core's repost (amplification) signal.
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

API = "https://public.api.bsky.app/xrpc/"
POST_URL = re.compile(r"^(?:https?://)?(?:www\.)?bsky\.app/profile/([A-Za-z0-9.:_-]+)/post/([A-Za-z0-9]+)/?(?:[?#].*)?$", re.I)
MAX_PARTICIPANTS = 200    # participants whose history and profile are fetched; the rest keep their thread posts only
MAX_HISTORY = 100         # getAuthorFeed gives at most 100 per call


class NotABlueskyPost(ValueError):
    pass


def is_bluesky(url):
    return bool(POST_URL.match((url or "").strip()))


def _name(author):
    """The handle as Bluesky shows it; the DID when the handle is broken (they would all be 'handle.invalid')."""
    handle = author.get("handle") or ""
    return handle if handle and handle != "handle.invalid" else author.get("did") or handle


def _links(record):
    urls = []
    for facet in record.get("facets") or []:
        for f in facet.get("features") or []:
            if f.get("uri"):
                urls.append(f["uri"])
    ext = ((record.get("embed") or {}).get("external") or {}).get("uri")
    if ext:
        urls.append(ext)
    return " ".join(dict.fromkeys(u.replace(" ", "%20") for u in urls))


def _post_row(post):
    rec = post.get("record") or {}
    reply = rec.get("reply") or {}
    return {
        "comment_id": post["uri"],
        "username": _name(post["author"]),
        "timestamp": rec.get("createdAt") or post.get("indexedAt") or "",
        "text": rec.get("text") or "",
        "links": _links(rec),
        "parent_id": (reply.get("parent") or {}).get("uri") or "",
        "thread_id": (reply.get("root") or {}).get("uri") or post["uri"],
        "repost_of": "",
    }


class Bluesky:
    def __init__(self, client, workers=None):
        self.client = client
        self.workers = workers or client.workers
        self.via = {}                     # "context.dev" / "direct" -> number of requests
        self._lock = threading.Lock()

    def _get(self, method, **params):
        pairs = [(k, x) for k, v in params.items() for x in (v if isinstance(v, list) else [v])]
        q = "&".join(f"{k}={quote(str(x), safe='')}" for k, x in pairs)   # a list repeats its parameter: actors=a&actors=b
        data, via = self.client.fetch_json(f"{API}{method}?{q}")
        with self._lock:
            self.via[via] = self.via.get(via, 0) + 1
        return data

    def _uri(self, url):
        m = POST_URL.match((url or "").strip())
        if not m:
            raise NotABlueskyPost("Not a Bluesky post link. It should look like https://bsky.app/profile/NAME/post/ID.")
        actor, rkey = m.groups()
        if actor.lower().startswith("did:"):
            did = actor
        else:
            try:
                did = self._get("com.atproto.identity.resolveHandle", handle=actor.lower()).get("did")
            except Exception:
                did = None
        if not did:
            raise NotABlueskyPost(f"Bluesky does not know the account {actor}.")
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def thread(self, url):
        """(root post, [root + every reply that is public], number of replies Bluesky would not give)."""
        try:
            data = self._get("app.bsky.feed.getPostThread", uri=self._uri(url), depth=1000, parentHeight=0)
        except NotABlueskyPost:
            raise
        except RecursionError:
            raise NotABlueskyPost("This thread is nested too deeply to read.") from None
        except Exception as e:
            raise NotABlueskyPost(f"The post was not found, or it is not public. ({str(e)[:120]})") from None
        root = data.get("thread") or {}
        if not root.get("post"):
            raise NotABlueskyPost("The post was not found, or it is not public.")
        posts, hidden, seen = [root["post"]], 0, {root["post"]["uri"]}
        stack = [root]                   # a loop, not recursion: a reply chain can be 1000 deep
        while stack:
            node = stack.pop()
            for r in reversed(node.get("replies") or []):
                post = r.get("post")
                if not post or not post.get("uri") or not (post.get("author") or {}).get("did"):
                    hidden += 1          # blocked or deleted replies
                elif post["uri"] not in seen:
                    seen.add(post["uri"])
                    posts.append(post)
                    stack.append(r)
        return root["post"], posts, hidden

    def history(self, did, limit):
        try:
            data = self._get("app.bsky.feed.getAuthorFeed", actor=did, limit=max(1, min(int(limit), MAX_HISTORY)),
                             filter="posts_with_replies")
        except Exception as e:  # one account failing must not stop the rest
            return {"did": did, "status": "failed", "error": str(e)[:200], "feed": []}
        return {"did": did, "status": "ok", "feed": data.get("feed") or []}

    def profiles(self, dids):
        out = {}
        for i in range(0, len(dids), 25):
            try:
                data = self._get("app.bsky.actor.getProfiles", actors=dids[i:i + 25])
            except Exception:
                continue
            for p in data.get("profiles") or []:
                out[p["did"]] = p
        return out

    def collect(self, url, history=30, on_progress=None, on_thread=None, max_participants=None):
        root, posts, hidden = self.thread(url)
        comments = {p["uri"]: _post_row(p) for p in posts}
        people = {}
        for p in posts:
            people.setdefault(p["author"]["did"], p["author"])
        dids = list(people)[:max_participants or MAX_PARTICIPANTS]
        if on_thread:
            on_thread(len(posts) - 1, len(people), len(dids))

        done = [0]

        def one(did):
            h = self.history(did, history)
            with self._lock:
                done[0] += 1
                n = done[0]
            if on_progress:
                on_progress(n, len(dids))
            return h

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            histories = list(pool.map(one, dids))

        reposts = 0
        for h in histories:
            for item in h["feed"]:
                post, reason = item.get("post") or {}, item.get("reason") or {}
                if not post.get("uri"):
                    continue
                if reason.get("$type", "").endswith("reasonRepost"):
                    by = _name(people[h["did"]])
                    rid = f"repost:{by}:{post['uri']}"
                    if rid not in comments and post.get("author", {}).get("did") != h["did"]:
                        comments[rid] = {"comment_id": rid, "username": by, "timestamp": reason.get("indexedAt") or "",
                                         "text": "", "links": "", "parent_id": "", "thread_id": "", "repost_of": post["uri"]}
                        reposts += 1
                elif post["uri"] not in comments and post.get("author", {}).get("did") == h["did"]:
                    comments[post["uri"]] = _post_row(post)

        prof = self.profiles(dids)
        profiles = []
        for did in dids:
            p = prof.get(did) or {}
            profiles.append({
                "username": _name(people[did]),          # the same name as on this account's comments
                "created_at": p.get("createdAt") or people[did].get("createdAt") or "",
                "display_name": p.get("displayName") or people[did].get("displayName") or "",
                "bio": " ".join((p.get("description") or "").split()),
                "followers": p.get("followersCount", ""),
                "following": p.get("followsCount", ""),
                "post_count": p.get("postsCount", ""),
                "default_avatar": "" if not p else ("0" if p.get("avatar") else "1"),
            })

        rec = root.get("record") or {}
        return {
            "thread": {"platform": "Bluesky", "title": (rec.get("text") or "")[:140], "author": _name(root["author"]),
                       "url": url, "post_id": root["uri"],
                       "comments_found": len(posts) - 1,
                       # Bluesky's own count of replies under every post we read; replyCount of the root alone is direct replies only
                       "comments_expected": sum(p.get("replyCount") or 0 for p in posts),
                       "direct_replies_expected": root.get("replyCount"),
                       "comments_hidden": hidden, "commenters": len(people), "commenters_fetched": len(dids),
                       "history_per_commenter": history},
            "comments": list(comments.values()),
            "profiles": profiles,
            "histories_ok": sum(1 for h in histories if h["status"] == "ok"),
            "histories_failed": sum(1 for h in histories if h["status"] == "failed"),
            "reposts": reposts,
            "via": dict(self.via),
        }
