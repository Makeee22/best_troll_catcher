"""Context.dev client for the website: fetches Reddit users' recent comments.

Server-side only. The API key comes from the environment (CONTEXT_DEV_API_KEY, set in the
server's .env); it is never logged or returned to the browser.

    client = ContextDev.from_env()
    histories = client.reddit_histories(["alice", "bob"], limit=25, on_progress=print)
    comments, profiles = to_rows(histories)

Uses the prebuilt parser "reddit-user" of POST /v1/web/scrape (docs.context.dev/scrape/prebuilt-parsers).
Plain urllib, so the image needs no new dependency.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.context.dev/v1/web/scrape"
USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,20}$")      # Reddit's own rule for usernames
SKIP = {"[deleted]", "automoderator", "deleted"}


class ContextDevError(Exception):
    """A failure the user should see as it is (no key, no credits, bad answer)."""


class ContextDev:
    def __init__(self, api_key, workers=2, timeout=90):
        if not api_key:
            raise ContextDevError("Context.dev is not configured on this server (CONTEXT_DEV_API_KEY is missing).")
        self._key = api_key
        self.workers = max(1, workers)
        self.timeout = timeout
        self._cache = {}                 # (username, limit) -> history; lives as long as the process
        self._lock = threading.Lock()
        self.credits_used = 0
        self.credits_remaining = None

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("CONTEXT_DEV_API_KEY", "").strip(),
                   workers=int(os.environ.get("CONTEXT_DEV_WORKERS", "2")))

    def _post(self, body):
        """POST with retries on 429 (concurrency or per-minute limit) and on network errors."""
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(API, data=data, method="POST", headers={
                "Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                meta = out.get("key_metadata") or {}
                with self._lock:
                    self.credits_used += meta.get("credits_consumed") or 0
                    if meta.get("credits_remaining") is not None:
                        self.credits_remaining = meta["credits_remaining"]
                return out
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode(errors="replace"))
                except ValueError:
                    err = {}
                code = err.get("error_code") or ""
                if e.code == 429:
                    wait = float(e.headers.get("Retry-After") or (err.get("error_data") or {}).get("retry_after_seconds") or 2)
                    time.sleep(min(60, wait) + attempt)
                    continue
                if e.code == 402 or (e.code == 401 and code == "USAGE_EXCEEDED"):
                    raise ContextDevError("Context.dev credits have run out.") from None
                if e.code == 401:
                    raise ContextDevError("Context.dev rejected the API key.") from None
                if e.code >= 500 and attempt < 2:
                    time.sleep(2)
                    continue
                return {"_http_error": e.code, "_error_code": code, "_message": err.get("message")}
            except (urllib.error.URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(2)
                    continue
                return {"_http_error": 0, "_error_code": "NETWORK", "_message": "no answer from Context.dev"}
        return {"_http_error": 429, "_error_code": "RATE_LIMITED", "_message": "still rate limited after retries"}

    def reddit_history(self, username, limit=25):
        """One user's newest comments (and account data). Returns a dict with 'status'."""
        key = (username.lower(), limit)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        out = self._post({
            "url": f"https://www.reddit.com/user/{username}/comments/?sort=new",
            "formats": {"parse": True},
            "parseParams": {"type": "prebuilt", "parser": "reddit-user", "limit": limit},
        })
        parsed = out.get("parsed") or {}
        if out.get("_http_error") is not None or not parsed.get("success"):
            code = out.get("_error_code") or parsed.get("error_code") or "UNKNOWN"
            result = {"username": username, "status": "failed", "error": code}
        else:
            data = parsed.get("data") or {}
            user = data.get("user") or {}
            comments = data.get("comments")
            result = {
                "username": user.get("username") or username,
                "status": "suspended" if comments is None else "ok",
                "created_at": user.get("created_at"),
                "comments": comments or [],
            }
        if result["status"] != "failed":   # failures are retried next time
            with self._lock:
                self._cache[key] = result
        return result

    def reddit_histories(self, usernames, limit=25, on_progress=None):
        """Fetch many users with a small worker pool. on_progress(done, total) after each user."""
        names = []
        for u in usernames:
            u = re.sub(r"^/?u(?:ser)?/", "", (u or "").strip()).strip("/")
            if USERNAME.match(u) and u.lower() not in SKIP and u.lower() not in {n.lower() for n in names}:
                names.append(u)
        done = 0
        results = []
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for result in pool.map(lambda n: self.reddit_history(n, limit), names):
                results.append(result)
                done += 1
                if on_progress:
                    on_progress(done, len(names))
        return results


def to_rows(histories, thread_comments=()):
    """Histories (+ the thread's own comments) -> rows for comments.csv and profiles.csv.

    thread_comments: dicts with comment_id, username, timestamp, text, parent_id, thread_id.
    A comment that is in the thread and in a history is kept once (by comment_id).
    """
    comments, seen = [], set()
    for c in thread_comments:
        if c.get("comment_id") and c["comment_id"] in seen:
            continue
        seen.add(c.get("comment_id"))
        comments.append(c)
    profiles = []
    for h in histories:
        if h["status"] == "failed":
            continue
        profiles.append({"username": h["username"], "created_at": h.get("created_at") or ""})
        for c in h["comments"]:
            cid = c.get("id")
            if not cid or cid in seen or not c.get("body"):
                continue
            seen.add(cid)
            comments.append({
                "comment_id": cid,
                "username": h["username"],
                "timestamp": c.get("posted_at") or "",
                "text": c["body"],
                "parent_id": c.get("parent_id") or "",
                "thread_id": (c.get("post") or {}).get("id") or "",
            })
    return comments, profiles
