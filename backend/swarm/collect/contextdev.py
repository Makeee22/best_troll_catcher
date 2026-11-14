"""Context.dev client for the collector, ported from frontend/api/contextdev.py (which stays until the site switches).

The key comes from CONTEXT_DEV_API_KEY and is never logged or put in a bundle. Without a key the client still
builds: public JSON endpoints are fetched directly, and anything that needs Context.dev raises a CollectError.
Plain urllib, so the core's image needs no new dependency.
"""
import base64
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

API = "https://api.context.dev/v1/web/scrape"
JSON_TIMEOUT = 10     # seconds to wait for Context.dev in fetch_json before asking the site directly


class CollectError(ValueError):
    """A failure the user should see as it is (unsupported link, post not found, no key, no credits)."""


class ContextDevError(CollectError):
    pass


class ContextDev:
    def __init__(self, api_key, workers=2, timeout=90):
        self._key = api_key or ""
        self.workers = max(1, workers)
        self.timeout = timeout
        self._cache = {}                 # (url, parser, limit) -> parsed object; lives as long as the client
        self._lock = threading.Lock()
        self.credits_used = 0
        self.credits_remaining = None
        self._json_pool = ThreadPoolExecutor(max_workers=self.workers * 4, thread_name_prefix="contextdev-json")
        self.rate_limited = 0            # 429 answers so far (each one is waited out and retried)

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("CONTEXT_DEV_API_KEY", "").strip(), workers=int(os.environ.get("CONTEXT_DEV_WORKERS", "2")))

    def _post(self, body, timeout=None, patient=True):
        """POST with retries on 429 (concurrency or per-minute limit) and on network errors.

        patient=False: give up at the first timeout or 5xx (for callers that have another way to get the data).
        """
        if not self._key:
            raise ContextDevError("This site needs Context.dev: set CONTEXT_DEV_API_KEY.")
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(API, data=data, method="POST", headers={
                "Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                    out = json.load(r)
                if not isinstance(out, dict):
                    raise ValueError("not a JSON object")
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
            except (OSError, http.client.HTTPException, ValueError):   # no answer, a cut-off or a non-JSON body
                if attempt < 2 and patient:
                    time.sleep(2)
                    continue
                return {"_http_error": 0, "_error_code": "NETWORK", "_message": "no answer from Context.dev"}
        return {"_http_error": 429, "_error_code": "RATE_LIMITED", "_message": "still rate limited after retries"}

    def direct_json(self, url):
        return direct_json(url)

    def fetch_json(self, url):
        """A public JSON endpoint fetched through Context.dev: the original response body (formats.bytes).

        Falls back to a direct request when Context.dev cannot give it (no key, an error, no credits, a body
        that is not a JSON object), so a collector of public data keeps working.
        Returns (data, via) where via is "context.dev" or "direct". Raises CollectError when both fail.
        """
        if not self._key:
            return direct_json(url), "direct"
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
        return direct_json(url), "direct"

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

    def parse(self, url, parser, limit=None):
        """A prebuilt parser's `parsed` object exactly as Context.dev returned it.

        On a failure: {"type": parser, "success": False, "error_code": ...}. Only successes are cached.
        """
        key = (url, parser, limit)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        params = {"type": "prebuilt", "parser": parser, **({"limit": limit} if limit else {})}
        out = self._post({"url": url, "formats": {"parse": True}, "parseParams": params})
        parsed = out.get("parsed") if out.get("_http_error") is None else None
        if not isinstance(parsed, dict) or not parsed.get("success"):
            code = out.get("_error_code") or (parsed or {}).get("error_code") or "UNKNOWN"
            return {"type": parser, "success": False, "error_code": code}
        with self._lock:
            self._cache[key] = parsed
        return parsed


def direct_json(url, timeout=30):
    """Plain GET of a public, login-free JSON endpoint. Raises ContextDevError unless a JSON object comes back."""
    req = urllib.request.Request(url, headers={"User-Agent": "spot-the-swarm (Junction 2026 hackathon)", "Accept": "application/json"})
    short = url.split("?")[0]
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
            raise ContextDevError(f"The site answered {e.code} for {short}") from None
        except (OSError, http.client.HTTPException):   # URLError, timeouts, resets, a body cut off mid-read
            if attempt < 2:
                time.sleep(2)
                continue
            raise ContextDevError(f"No answer from {short}") from None
        except ValueError:
            raise ContextDevError(f"{short} did not answer with JSON") from None
        if not isinstance(data, dict):
            raise ContextDevError(f"{short} did not answer with a JSON object")
        return data
