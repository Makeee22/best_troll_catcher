"""Reddit thread analysis as a background job, visible only through its own random id.

POST /api/jobs/reddit                 multipart "page": a Reddit thread page saved from the browser (HTML)
                                      -> 202 {"id", "thread": {...}}; 400 if it is not a Reddit thread
GET  /api/jobs/{id}                   status, progress, and when done the listing (same shape as GET /api/swarms)
GET  /api/jobs/{id}/swarms/{swarm}    one cluster, same shape as GET /api/swarms/{id}

Steps: read the thread's comments and commenters from the page, fetch each commenter's recent
Reddit comments with Context.dev, run swarm.core.analyze() on thread + histories.

Privacy: results stay in memory only, for JOB_TTL seconds, and are reachable only by the job id
(not listed anywhere, not shown to other visitors). Nothing is written to disk except the
temporary CSV files of one analysis, deleted right after it. A cap on jobs per hour keeps the
site from being used for mass profiling.
"""
import csv
import secrets
import tempfile
import threading
import time
from pathlib import Path

from fastapi import File, HTTPException, UploadFile

import contextdev
import reddit_html

MAX_PAGE_BYTES = 15 * 1024 * 1024
HISTORY = 25          # newest comments per commenter (B11: ~15; 25 for margin, 1 credit each either way)
MAX_USERS = 150       # commenters whose history is fetched; the rest are analysed on their thread comments only
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
            "swarms": [{"id": c["id"], "size": c["size"], "confidence": c["confidence"], "edge_count": c["edge_count"],
                        "first_seen": c["first_seen"], "last_seen": c["last_seen"],
                        "sample": c["top_items"][0] if c["top_items"] else None,
                        "declared_automation": c.get("declared_automation")}   # same shape as backend/swarm/api.py
                       for c in r["clusters"]],
        }
        out["metrics"] = {"source": r["source"], "metrics": r["metrics"]}
    return out


def _write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _run(job, thread, analyze, analysis_lock):
    t0 = time.time()
    try:
        client = _client_or_error()
        authors = thread["authors"][:MAX_USERS]
        job["stage"] = f"Fetching the recent comments of {len(authors)} commenters"

        def progress(done, total):
            job["progress"] = {"done": done, "total": total}

        before = client.credits_used
        histories = client.reddit_histories(authors, limit=HISTORY, on_progress=progress)
        job["credits_used"] = client.credits_used - before
        job["histories_ok"] = sum(1 for h in histories if h["status"] == "ok")
        job["histories_failed"] = sum(1 for h in histories if h["status"] == "failed")

        comments, profiles = contextdev.to_rows(histories, thread["comments"])
        job["status"], job["stage"] = "analysing", "Looking for accounts that act together"
        with tempfile.TemporaryDirectory(prefix="swarm-job-") as work:
            cpath, ppath = Path(work, "comments.csv"), Path(work, "profiles.csv")
            _write_csv(cpath, comments, ["comment_id", "username", "timestamp", "text", "parent_id", "thread_id"])
            _write_csv(ppath, profiles, ["username", "created_at"])
            with analysis_lock:
                result = analyze(str(cpath), str(ppath))
        post = thread["post"] or {}
        result["source"]["comments_file"] = f"{post.get('subreddit') or 'Reddit'} thread {post.get('id') or ''}".strip()
        result["source"]["profiles_file"] = f"recent comments of {job['histories_ok']} commenters (Context.dev)"
        job["result"] = result
        job["status"], job["stage"] = "done", "Done"
    except contextdev.ContextDevError as e:
        job["status"], job["error"] = "failed", str(e)
    except Exception as e:  # the core's InputError and anything unexpected: show a short message, keep the server up
        job["status"], job["error"] = "failed", f"The analysis failed: {type(e).__name__}: {str(e)[:300]}"
    finally:
        job["seconds"] = round(time.time() - t0, 1)


def register(app, analyze, analysis_lock):
    @app.post("/api/jobs/reddit", status_code=202)
    def start_reddit_job(page: UploadFile = File(...)):
        _cleanup()
        raw = page.file.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise HTTPException(413, "The saved page is larger than 15 MB.")
        try:
            thread = reddit_html.parse_thread(raw)
        except reddit_html.NotARedditThread as e:
            raise HTTPException(400, str(e)) from None
        if not thread["authors"]:
            raise HTTPException(400, "No commenters found in the saved page. Scroll down so the comments load, then save again.")
        try:
            _client_or_error()
        except contextdev.ContextDevError as e:
            raise HTTPException(503, str(e)) from None
        with _lock:
            if sum(1 for j in _jobs.values() if j["status"] in ("collecting", "analysing")) >= RUNNING_MAX:
                raise HTTPException(429, "Two analyses are already running. Try again in a minute.")
            if len(_started) >= JOBS_PER_HOUR:
                raise HTTPException(429, f"This demo allows {JOBS_PER_HOUR} thread analyses per hour. Try again later.")
            _started.append(time.time())
            post = thread["post"] or {}
            job = {
                "id": secrets.token_urlsafe(12), "created": time.time(), "status": "collecting",
                "stage": "Starting", "progress": {"done": 0, "total": min(len(thread["authors"]), MAX_USERS)},
                "thread": {"subreddit": post.get("subreddit"), "title": post.get("title"), "post_id": post.get("id"),
                           "comments_found": thread["found"], "comments_expected": thread["expected"],
                           "commenters": len(thread["authors"]), "history_per_commenter": HISTORY,
                           "commenters_fetched": min(len(thread["authors"]), MAX_USERS)},
                "error": None, "credits_used": 0, "histories_ok": 0, "histories_failed": 0, "seconds": None, "result": None,
            }
            _jobs[job["id"]] = job
        threading.Thread(target=_run, args=(job, thread, analyze, analysis_lock), daemon=True).start()
        return _public(job)

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
