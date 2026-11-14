"""Discussion analysis as a background job, visible only through its own random id.

POST /api/jobs/url                    JSON {"url": "..."}: a Bluesky post link (https://bsky.app/profile/NAME/post/ID)
                                      -> 202 {"id", ...}; 400 for a Reddit link (use the saved page) or any other site
POST /api/jobs/reddit                 multipart "page": a Reddit thread page saved from the browser (HTML)
                                      -> 202 {"id", "thread": {...}}; 400 if it is not a Reddit thread
GET  /api/jobs/{id}                   status, progress, and when done the listing (same shape as GET /api/swarms)
GET  /api/jobs/{id}/swarms/{swarm}    one cluster, same shape as GET /api/swarms/{id}

Steps for a link: the backend's collector (swarm.collect: Bluesky, Reddit, Hacker News, review sites) fetches the
discussion and each participant's recent public history, then swarm.collect.analyse() converts and runs the core with
the similar-text signal. A saved Reddit page still goes through contextdev.py + swarm.convert here.

Privacy: results stay in memory only, for JOB_TTL seconds, and are reachable only by the job id
(not listed anywhere, not shown to other visitors). Nothing is written to disk except the
temporary CSV files of one analysis, deleted right after it. A cap on jobs per hour keeps the
site from being used for mass profiling.
"""
import csv
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel

import bluesky
import contextdev
import reddit_html    # only for the thread's title and subreddit; comments come from the backend's converter
from swarm import collect as swarm_collect
from swarm.convert import ConvertError, convert as convert_bundle
from swarm.load import COMMENT_COLUMNS, InputError, PROFILE_COLUMNS

MAX_PAGE_BYTES = 100 * 1024 * 1024   # a saved Reddit page; keep in step with app.js and client_max_body_size in nginx.conf
                                     # (measured: a 75 MB page converts in ~46 s with ~370 MB of Python memory)
HISTORY = 25          # newest comments per commenter (B11: ~15; 25 for margin, 1 credit each either way)
MAX_USERS = 150       # commenters whose history is fetched; the rest are analysed on their thread comments only
BLUESKY_HISTORY = 30  # newest posts, replies and reposts per participant (1 request each)
MAX_PARTICIPANTS = 150   # Bluesky participants whose history is fetched; the rest keep their thread posts only
REDDIT_LINK = re.compile(r"^(?:https?://)?(?:[\w-]+\.)?(?:reddit\.com|redd\.it)(?:/|$)", re.I)
COMMENT_FIELDS = ["comment_id", "username", "timestamp", "text", "links", "parent_id", "thread_id", "repost_of"]
PROFILE_FIELDS = ["username", "created_at", "display_name", "bio", "followers", "following", "post_count", "default_avatar"]
JOB_TTL = 3 * 3600
JOBS_PER_HOUR = 20
RUNNING_MAX = 2

_jobs = {}
_lock = threading.Lock()
_started = []         # start times, for the hourly cap
_client = None


def _client_or_error():
    global _client
    if _client is None:
        _client = contextdev.ContextDev.from_env()   # raises ContextDevError when the key is missing
    return _client


def _cleanup():
    now = time.time()
    with _lock:
        for jid in [j for j, v in _jobs.items() if now - v["created"] > JOB_TTL]:
            del _jobs[jid]
        _started[:] = [t for t in _started if now - t < 3600]


def _public(job):
    """What the browser may see of a job."""
    out = {k: job[k] for k in ("id", "status", "stage", "progress", "thread", "error", "credits_used",
                                "histories_ok", "histories_failed", "seconds")}
    if job["status"] == "done":
        r = job["result"]
        out["listing"] = {
            "source": r["source"], "parameters": r["parameters"], "signals": r["signals"], "warnings": r["warnings"],
            "diagnostics": r.get("diagnostics"), "collection": r.get("collection"),   # handoff 6f.1, docs/api.md
            "swarms": [{"id": c["id"], "size": c["size"], "confidence": c["confidence"], "edge_count": c["edge_count"],
                        "first_seen": c["first_seen"], "last_seen": c["last_seen"],
                        "sample": c["top_items"][0] if c["top_items"] else None,
                        "declared_automation": c.get("declared_automation"),
                        "flagged_members": c.get("flagged_members", c["size"])}   # same shape as backend/swarm/api.py
                       for c in r["clusters"]],
        }
        out["metrics"] = {"source": r["source"], "metrics": r["metrics"]}
    return out


def _write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _fields(preferred, rows):
    """Columns present in the rows that the core reads (swarm.load); extra converter columns would only add warnings."""
    known = COMMENT_COLUMNS if preferred is COMMENT_FIELDS else PROFILE_COLUMNS
    present = {k for r in rows for k in r}
    return [f for f in dict.fromkeys(list(preferred) + list(known)) if f in present]


class UrlJob(BaseModel):
    url: str


def _collect_reddit(job, client, bundle, authors, post):
    """-> (comment rows, profile rows, label of the comments, label of the profiles, warnings)

    Collect = the histories; convert = the backend's swarm.convert (docs/collect-interface.md,
    "How to call the converter"): the thread page plus one profile page per fetched history.
    """
    authors = authors[:MAX_USERS]
    job["stage"] = f"Fetching the recent comments of {len(authors)} commenters"

    def progress(done, total):
        job["progress"] = {"done": done, "total": total}

    histories = client.reddit_histories(authors, limit=HISTORY, on_progress=progress)
    job["histories_ok"] = sum(1 for h in histories if h["status"] == "ok")
    job["histories_failed"] = sum(1 for h in histories if h["status"] == "failed")
    for h in histories:
        if h["status"] != "failed":
            bundle["pages"].append({"url": f"https://www.reddit.com/user/{h['username']}", "role": "profile",
                                    "parsed": {"type": "reddit-user", "success": True,
                                               "data": {"user": {"username": h["username"], "created_at": h.get("created_at")},
                                                        "comments": h["comments"]}}})
    comments, profiles, notes = convert_bundle(bundle)
    if job["histories_failed"]:
        notes = [f"thread: the recent comments of {job['histories_failed']} commenters could not be fetched"] + list(notes)
    return (comments, profiles, f"{post.get('subreddit') or 'Reddit'} thread {post.get('id') or ''}".strip(),
            f"recent comments of {job['histories_ok']} commenters (Context.dev)", list(notes))


def _reddit_bundle(raw):
    """Saved or fetched thread page -> (bundle, authors, post meta, comment rows); raises ConvertError."""
    try:
        post = reddit_html.parse_thread(raw)["post"] or {}
    except reddit_html.NotARedditThread:
        post = {}
    url = "https://www.reddit.com/" + (f"comments/{post['id']}/" if post.get("id") else "")
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    bundle = {"url": url, "site": "reddit", "pages": [{"url": url, "role": "thread", "html": text}]}
    rows, _, _ = convert_bundle(bundle)
    rows = [r for r in rows if r.get("comment_id") != post.get("id")]   # the converter also returns the post itself
    authors = list(dict.fromkeys(r["username"] for r in rows))          # anonymous and [deleted] are already gone
    return bundle, authors, post, rows


def _reddit_thread_meta(post, rows, authors):
    return {"platform": "Reddit", "subreddit": post.get("subreddit"), "title": post.get("title"), "post_id": post.get("id"),
            "comments_found": len(rows), "comments_expected": post.get("comment_count"),
            "commenters": len(authors), "history_per_commenter": HISTORY, "commenters_fetched": min(len(authors), MAX_USERS)}


def _collect_reddit_url(job, client, url):
    """A Reddit thread link: Context.dev renders the page (what a browser shows before 'load more'), then as a saved page."""
    job["stage"] = "Reading the thread"
    html = client.fetch_html(url, must_contain="<shreddit-comment ")
    if not html:
        raise contextdev.ContextDevError("Reddit did not show the comments this time (it sometimes answers with a bot check). "
                                         "Try again in a minute, or save the thread page and use the Reddit card.")
    try:
        bundle, authors, post, rows = _reddit_bundle(html)
    except ConvertError:
        raise contextdev.ContextDevError("No comments found on that Reddit page.") from None
    if not authors:
        raise contextdev.ContextDevError("No commenters found on that Reddit page.")
    job["thread"] = {**_reddit_thread_meta(post, rows, authors), "url": url}
    job["progress"] = {"done": 0, "total": job["thread"]["commenters_fetched"]}
    return _collect_reddit(job, client, bundle, authors, post)


def _collect_bluesky(job, client, url):
    job["stage"] = "Reading the thread"

    def on_thread(replies, people, fetched):
        job["thread"].update(comments_found=replies, commenters=people, commenters_fetched=fetched)
        job["progress"] = {"done": 0, "total": fetched}
        job["stage"] = f"Fetching the recent posts and reposts of {fetched} participants"

    def progress(done, total):
        job["progress"] = {"done": done, "total": total}

    data = bluesky.Bluesky(client).collect(url, history=BLUESKY_HISTORY, on_progress=progress, on_thread=on_thread,
                                           max_participants=MAX_PARTICIPANTS)
    t = data["thread"]
    job["thread"] = {**t, "reposts": data["reposts"], "via": data["via"]}
    job["histories_ok"], job["histories_failed"] = data["histories_ok"], data["histories_failed"]
    notes = []
    missing = (t["comments_expected"] or 0) - t["comments_found"]
    if missing > 0:
        notes.append(f"thread: Bluesky counts {t['comments_expected']} replies, {t['comments_found']} could be read; "
                     f"the other {missing} are deleted, hidden or blocked")
    if t["commenters"] > t["commenters_fetched"]:
        notes.append(f"thread: {t['commenters']} participants, recent posts were fetched for the first {t['commenters_fetched']}; "
                     "the others are judged on their posts in this thread only")
    if data["histories_failed"]:
        notes.append(f"thread: the recent posts of {data['histories_failed']} participants could not be fetched")
    used = data["via"]
    how = "Context.dev" if set(used) == {"context.dev"} else "directly from Bluesky" if set(used) == {"direct"} else \
        f"Context.dev, {used.get('direct', 0)} of {sum(used.values())} requests directly from Bluesky"
    return (data["comments"], data["profiles"], f"Bluesky thread by @{t['author']}",
            f"recent posts and reposts of {data['histories_ok']} participants ({how})", notes)


def _run(job, collect, analyze, analysis_lock):
    t0 = time.time()
    try:
        client = _client_or_error()
        before = client.credits_used
        try:
            comments, profiles, comments_label, profiles_label, notes = collect(job, client)
        finally:
            job["credits_used"] = client.credits_used - before
        job["status"], job["stage"] = "analysing", "Looking for accounts that act together"
        with tempfile.TemporaryDirectory(prefix="swarm-job-") as work:
            cpath, ppath = Path(work, "comments.csv"), Path(work, "profiles.csv")
            _write_csv(cpath, comments, _fields(COMMENT_FIELDS, comments))
            _write_csv(ppath, profiles, _fields(PROFILE_FIELDS, profiles))
            with analysis_lock:
                try:
                    result = analyze(str(cpath), str(ppath) if profiles else None, similar_text=True)
                except InputError as e:   # the similar-text model is missing: still worth a run without it
                    if "similar-text" not in str(e):
                        raise
                    notes = notes + [f"similar-text signal skipped: {e}"]
                    result = analyze(str(cpath), str(ppath) if profiles else None)
        result["source"]["comments_file"] = comments_label
        result["source"]["profiles_file"] = profiles_label
        result["warnings"] = notes + list(result.get("warnings") or [])
        job["result"] = result
        job["status"], job["stage"] = "done", "Done"
    except (contextdev.ContextDevError, bluesky.NotABlueskyPost) as e:
        job["status"], job["error"] = "failed", str(e)
    except Exception as e:  # the core's InputError and anything unexpected: show a short message, keep the server up
        job["status"], job["error"] = "failed", f"The analysis failed: {type(e).__name__}: {str(e)[:300]}"
    finally:
        job["seconds"] = round(time.time() - t0, 1)


_collector = None


def _run_link(job, url, analysis_lock):
    """A link through the backend's collector (docs/collect-interface.md, "Switching the site")."""
    global _collector
    t0 = time.time()
    try:
        if _collector is None:
            _collector = swarm_collect.ContextDev.from_env()
        job["stage"] = "Reading the thread"

        def progress(done, total):
            job["progress"] = {"done": done, "total": total}
            job["stage"] = f"Fetching the recent posts of {total} participants"

        history = BLUESKY_HISTORY if bluesky.is_bluesky(url) else HISTORY
        before = _collector.credits_used
        try:
            bundle = swarm_collect.collect(url, history=history, max_participants=None,   # the collector's own cap per site (handoff 6f.2)
                                           on_progress=progress, client=_collector)
        finally:
            job["credits_used"] = _collector.credits_used - before
        t, cov = bundle.get("thread") or {}, bundle.get("coverage") or {}
        job["thread"] = {**job["thread"], **t, "comments_found": cov.get("comments_found"),
                         "comments_expected": cov.get("comments_expected")}
        job["histories_ok"], job["histories_failed"] = t.get("histories_ok") or 0, t.get("histories_failed") or 0
        job["status"], job["stage"] = "analysing", "Looking for accounts that act together"
        with analysis_lock, tempfile.TemporaryDirectory(prefix="swarm-job-") as work:
            try:
                result = swarm_collect.analyse(bundle, work, similar_text=True)
            except (ConvertError, InputError) as e:    # e.g. a thread with no comments
                raise swarm_collect.CollectError(str(e)) from None
        job["result"] = result
        job["status"], job["stage"] = "done", "Done"
    except swarm_collect.CollectError as e:
        job["status"], job["error"] = "failed", str(e)
    except Exception as e:  # anything unexpected: show a short message, keep the server up
        job["status"], job["error"] = "failed", f"The analysis failed: {type(e).__name__}: {str(e)[:300]}"
    finally:
        job["seconds"] = round(time.time() - t0, 1)


def _start(thread, total, collect, analyze, analysis_lock):
    """Check the caps, register the job and start it. thread: what the page shows about the discussion."""
    try:
        _client_or_error()
    except contextdev.ContextDevError as e:
        raise HTTPException(503, str(e)) from None
    with _lock:
        if sum(1 for j in _jobs.values() if j["status"] in ("collecting", "analysing")) >= RUNNING_MAX:
            raise HTTPException(429, "Two analyses are already running. Try again in a minute.")
        if len(_started) >= JOBS_PER_HOUR:
            raise HTTPException(429, f"This demo allows {JOBS_PER_HOUR} discussion analyses per hour. Try again later.")
        _started.append(time.time())
        job = {
            "id": secrets.token_urlsafe(12), "created": time.time(), "status": "collecting",
            "stage": "Starting", "progress": {"done": 0, "total": total}, "thread": thread,
            "error": None, "credits_used": 0, "histories_ok": 0, "histories_failed": 0, "seconds": None, "result": None,
        }
        _jobs[job["id"]] = job
    if isinstance(collect, str):     # a link: the backend's collector does collect + convert + analyse
        threading.Thread(target=_run_link, args=(job, collect, analysis_lock), daemon=True).start()
    else:
        threading.Thread(target=_run, args=(job, collect, analyze, analysis_lock), daemon=True).start()
    return _public(job)


def register(app, analyze, analysis_lock):
    @app.post("/api/jobs/url", status_code=202)
    def start_url_job(body: UrlJob):
        _cleanup()
        url = body.url.strip()
        if len(url) > 500 or any(c.isspace() for c in url):
            raise HTTPException(400, "That does not look like a link.")
        if REDDIT_LINK.match(url) and not re.search(r"/comments/[A-Za-z0-9]+", url):
            raise HTTPException(400, "Give the link of one Reddit thread: https://www.reddit.com/r/NAME/comments/ID/...")
        if re.match(r"^(?:https?://)?(?:www\.)?bsky\.app(?:/|$)", url, re.I) and not bluesky.is_bluesky(url):
            raise HTTPException(400, "Give the link of one Bluesky post: https://bsky.app/profile/NAME/post/ID.")
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if not any(mod.matches(url) for _, mod in swarm_collect.SITES):
            raise HTTPException(400, "This site is not supported yet. Links that work: a Bluesky post, a Reddit thread, "
                                     "a Hacker News story, or a review page (Google Maps, App Store, Google Play, Tripadvisor, Yelp, G2, TikTok).")
        platform = "Bluesky" if bluesky.is_bluesky(url) else "Reddit" if REDDIT_LINK.match(url) else None
        thread = {"platform": platform, "url": url, "title": None, "comments_found": None, "comments_expected": None,
                  "commenters": None, "history_per_commenter": BLUESKY_HISTORY if platform == "Bluesky" else HISTORY}
        return _start(thread, 0, url, analyze, analysis_lock)

    @app.post("/api/jobs/reddit", status_code=202)
    def start_reddit_job(page: UploadFile = File(...)):
        _cleanup()
        raw = page.file.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise HTTPException(413, f"The saved page is larger than {MAX_PAGE_BYTES // (1024 * 1024)} MB.")
        try:
            bundle, authors, post, rows = _reddit_bundle(raw)
        except ConvertError:
            raise HTTPException(400, "No Reddit comments found in this file. Open the thread on reddit.com, "
                                     "scroll so the comments load, then save the page (Ctrl+S) and choose that file.") from None
        if not authors:
            raise HTTPException(400, "No commenters found in the saved page. Scroll down so the comments load, then save again.")
        thread = _reddit_thread_meta(post, rows, authors)
        return _start(thread, thread["commenters_fetched"], lambda job, client: _collect_reddit(job, client, bundle, authors, post),
                      analyze, analysis_lock)

    def _get(job_id):
        _cleanup()
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "No such analysis. Results are kept for 3 hours, then deleted.")
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        return _public(_get(job_id))

    @app.get("/api/jobs/{job_id}/swarms/{swarm_id}")
    def job_swarm(job_id: str, swarm_id: str):
        job = _get(job_id)
        if job["status"] != "done":
            raise HTTPException(409, "The analysis is not finished yet.")
        for c in job["result"]["clusters"]:
            if c["id"] == swarm_id:
                return c
        raise HTTPException(404, "no such swarm")


def register_explain(app, explain_or_http, explain_result_or_http):
    """POST /api/jobs/{id}/swarms/{swarm}/explain: AI-written explanation of one cluster of a job (explain.py).
    POST /api/jobs/{id}/explain: the same for the job's whole result."""
    @app.post("/api/jobs/{job_id}/explain")
    def job_explain_result(job_id: str):
        _cleanup()
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "No such analysis. Results are kept for 3 hours, then deleted.")
        if job["status"] != "done":
            raise HTTPException(409, "The analysis is not finished yet.")
        return explain_result_or_http(("job-result", job_id), job["result"])

    @app.post("/api/jobs/{job_id}/swarms/{swarm_id}/explain")
    def job_explain(job_id: str, swarm_id: str):
        _cleanup()
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "No such analysis. Results are kept for 3 hours, then deleted.")
        if job["status"] != "done":
            raise HTTPException(409, "The analysis is not finished yet.")
        for c in job["result"]["clusters"]:
            if c["id"] == swarm_id:
                return explain_or_http(("job", job_id, swarm_id), c, job["result"]["source"])
        raise HTTPException(404, "no such swarm")
