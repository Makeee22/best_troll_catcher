"""Context.dev client for the website: Reddit users' recent comments, and public JSON endpoints (fetch_json).

Server-side only. The API key comes from the environment (CONTEXT_DEV_API_KEY, set in the
server's .env); it is never logged or returned to the browser.

    client = ContextDev.from_env()
    histories = client.reddit_histories(["alice", "bob"], limit=25, on_progress=print)
    comments, profiles = to_rows(histories)

Uses the prebuilt parser "reddit-user" of POST /v1/web/scrape (docs.context.dev/scrape/prebuilt-parsers).
Plain urllib, so the image needs no new dependency.
"""
import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

API = "https://api.context.dev/v1/web/scrape"
USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,20}$")      # Reddit's own rule for usernames
JSON_TIMEOUT = 10     # seconds to wait for Context.dev in fetch_json before asking the site directly
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
        self._json_pool = ThreadPoolExecutor(max_workers=self.workers * 4, thread_name_prefix="contextdev-json")
        self.rate_limited = 0            # 429 answers so far (each one is waited out and retried)

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("CONTEXT_DEV_API_KEY", "").strip(),
                   workers=int(os.environ.get("CONTEXT_DEV_WORKERS", "2")))

    def _post(self, body, timeout=None, patient=True):
        """POST with retries on 429 (concurrency or per-minute limit) and on network errors.

        patient=False: give up at the first timeout or 5xx (for callers that have another way to get the data).
        """
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(API, data=data, method="POST", headers={
                "Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
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
                    with self._lock:
                        self.rate_limited += 1
                    if not patient and attempt >= 1:
                        return {"_http_error": 429, "_error_code": "RATE_LIMITED", "_message": "rate limited"}
                    wait = float(e.headers.get("Retry-After") or (err.get("error_data") or {}).get("retry_after_seconds") or 2)
                    time.sleep((min(60, wait) if patient else min(3, wait)) + attempt)
                    continue
                if e.code == 402 or (e.code == 401 and code == "USAGE_EXCEEDED"):
                    raise ContextDevError("Context.dev credits have run out.") from None
                if e.code == 401:
                    raise ContextDevError("Context.dev rejected the API key.") from None
                if e.code >= 500 and attempt < 2 and patient:
                    time.sleep(2)
                    continue
                return {"_http_error": e.code, "_error_code": code, "_message": err.get("message")}
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < 2 and patient:
                    time.sleep(2)
                    continue
                return {"_http_error": 0, "_error_code": "NETWORK", "_message": "no answer from Context.dev"}
        return {"_http_error": 429, "_error_code": "RATE_LIMITED", "_message": "still rate limited after retries"}

    def fetch_json(self, url):
        """A public JSON endpoint fetched through Context.dev: the original response body (formats.bytes).

        Falls back to a direct request when Context.dev cannot give it (an error, no credits, a body
        that is not a JSON object), so a collector of public data keeps working.
        Returns (data, via) where via is "context.dev" or "direct". Raises ContextDevError when both fail.
        """
        # Mostly under a second, but now and then a request hangs for a minute or more: give it a deadline
        # on their side (timeoutOpts) and a hard one here, then ask the site itself.
        body = {"url": url, "formats": {"bytes": True}, "maxAgeMs": 600000, "timeoutOpts": {"milliseconds": JSON_TIMEOUT * 1000}}
        future = self._json_pool.submit(self._post, body, JSON_TIMEOUT + 2, False)
        try:
            out = future.result(timeout=JSON_TIMEOUT + 3)
        except (ContextDevError, FutureTimeout):
            out = {"_http_error": 408}
        body = ((out.get("bytes") or {}).get("data") or {}) if out.get("_http_error") is None else {}
        if isinstance(body, dict) and body.get("base64"):
            try:
                data = json.loads(base64.b64decode(body["base64"]).decode("utf-8"))
                if isinstance(data, dict) and not ("error" in data and "message" in data):
                    return data, "context.dev"
            except ValueError:
                pass
        return _direct_json(url), "direct"

    def fetch_html(self, url, wait_ms=6000, must_contain=None, tries=2):
        """A page's rendered HTML through Context.dev, or "" when it cannot be had.

        must_contain: a marker the page must have (e.g. '<shreddit-comment '); some sites first answer with an
        anti-bot check, so a page without it is fetched once more with a longer wait.
        """
        for attempt in range(tries):
            out = self._post({"url": url, "formats": {"html": True}, "maxAgeMs": 0,
                              "sharedParams": {"waitFor": wait_ms + 2000 * attempt}})
            html = ((out.get("html") or {}).get("data") or "") if out.get("_http_error") is None else ""
            if html and (must_contain is None or must_contain in html):
                return html
        return ""

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


def _direct_json(url, timeout=30):
    """Plain GET of a public, login-free JSON endpoint (fallback only)."""
    req = urllib.request.Request(url, headers={"User-Agent": "spot-the-swarm (Junction 2026 hackathon)", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
            raise ContextDevError(f"The site answered {e.code} for {url.split('?')[0]}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(2)
                continue
            raise ContextDevError(f"No answer from {url.split('?')[0]}") from None


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
