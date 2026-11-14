"""The real backend API (backend/swarm/api.py, unchanged) plus one upload endpoint.

Front-end owner's stand-in until the backend has its own upload endpoint (part 2 in
docs/core-design.md). Everything except POST /api/analyze comes from swarm.api, and
the upload runs swarm.core.analyze(), so the results are exactly the backend's.

POST /api/analyze
    multipart/form-data: "comments" (CSV, required), "profiles" (CSV, optional),
    both in the standard format of docs/api.md "Input files".
    200: the same body as GET /api/swarms for the uploaded data. The upload becomes
         the current result, so /api/swarms/{id} and /api/metrics answer for it.
    400: {"detail": "..."} when the core cannot analyse the input.
    413: the files together are larger than 20 MB.

Session model: ONE result in memory for everybody. An upload replaces it for all
visitors; a restart goes back to whatever swarm.api loads at startup (the synthetic
sample unless RESULT_FILE or COMMENTS_FILE is set).

    uvicorn app:app --port 8000      # from frontend/api/, with backend/ on the path

Also: discussion analysis jobs (POST /api/jobs/url for a Bluesky post link, POST /api/jobs/reddit for a saved
Reddit page, GET /api/jobs/{id}); see jobs.py.
Their results are per job and never replace the shared result above.
"""
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

from fastapi import File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
try:  # in the Docker image backend/swarm is copied next to this file
    import swarm.api as base
except ImportError:  # local run: use the backend code from the repo, read-only
    sys.path.insert(0, os.environ.get("BACKEND_DIR", str(HERE.parents[1] / "backend")))
    import swarm.api as base
from swarm.core import analyze
from swarm.load import InputError

MAX_BYTES = 20 * 1024 * 1024  # both files together; keep in step with client_max_body_size in frontend/nginx.conf
lock = threading.Lock()       # one analysis at a time: the VPS has 2 vCPUs

app = base.app


def _name(upload, fallback):
    """A safe file name that keeps the user's own name visible in source.comments_file."""
    name = os.path.basename((upload.filename or "").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ]", "_", name).strip(" .")[:100]
    return name or fallback


def _save(upload, folder, fallback, budget):
    data = upload.file.read(budget + 1)
    if len(data) > budget:
        raise HTTPException(413, f"The files are larger than {MAX_BYTES // (1024 * 1024)} MB together.")
    if not data.strip():
        raise HTTPException(400, f"{_name(upload, fallback)} is empty.")
    path = Path(folder) / fallback.split(".")[0] / _name(upload, fallback)
    path.parent.mkdir()
    path.write_bytes(data)
    return str(path), len(data)


@app.post("/api/analyze")
def upload(comments: UploadFile = File(...), profiles: UploadFile | None = File(None)):
    with tempfile.TemporaryDirectory(prefix="swarm-upload-") as work:
        comments_path, used = _save(comments, work, "comments.csv", MAX_BYTES)
        profiles_path = None
        if profiles is not None and profiles.filename:
            profiles_path, _ = _save(profiles, work, "profiles.csv", MAX_BYTES - used)
        with lock:
            try:
                result = analyze(comments_path, profiles_path)
            except InputError as e:
                message = str(e)  # the core names files by path: show the user's file name, not the server's temp dir
                for path in filter(None, (comments_path, profiles_path)):
                    message = message.replace(path, os.path.basename(path))
                raise HTTPException(400, message) from None
            base.result = result
            base.by_id = {c["id"]: c for c in result["clusters"]}
            return base.list_swarms()


# Discussion analysis (Bluesky link, saved Reddit page): background jobs, each visible only through its own id (jobs.py).
sys.path.insert(0, str(HERE))
import explain  # noqa: E402
import jobs  # noqa: E402

jobs.register(app, analyze, lock)


def explain_or_http(cache_key, cluster, source):
    """explain.explain() with its errors as HTTP answers the page can show."""
    try:
        return explain.explain(cache_key, cluster, source)
    except explain.ExplainError as e:
        raise HTTPException(429 if "per hour" in str(e) else 503, str(e)) from None


@app.post("/api/swarms/{swarm_id}/explain")
def explain_shared(swarm_id: str):
    """AI-written explanation of one cluster of the shared result (explain.py), cached per result and cluster."""
    if swarm_id not in base.by_id:
        raise HTTPException(404, "no such swarm")
    return explain_or_http(("shared", id(base.result), swarm_id), base.by_id[swarm_id], base.result["source"])


jobs.register_explain(app, explain_or_http)


# Local convenience only (no Docker, no nginx): serve the page from the same port.
# In the Docker image frontend/site does not exist and nginx serves it instead.
site = HERE.parent / "site"
if site.is_dir():
    app.mount("/samples", StaticFiles(directory=HERE.parent / "samples"))
    app.mount("/", StaticFiles(directory=site, html=True))
