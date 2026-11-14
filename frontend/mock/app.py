"""MOCK API for the front end. Not the real backend.

Serves the GET endpoints of docs/api.md with the same JSON shapes, and adds one
PROPOSED endpoint, POST /api/analyze (CSV upload). The real endpoint belongs to
the backend owner (Arde1001); see frontend/README.md for the proposal.

The detection itself is not mocked: backend/swarm/detect.py is imported
read-only, so the results are the same the real backend would give.

Session model: ONE dataset in memory for everybody. An upload replaces it for
all visitors, and a restart goes back to the synthetic sample. Good enough for
a demo; not for concurrent users.

    uvicorn app:app --reload --port 8000        # run from frontend/mock/
"""
import csv
import io
import os
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
try:  # in the Docker image backend/swarm is copied next to this file
    from swarm.detect import detect, evaluate, parse_time
    from swarm.synthetic import generate
except ImportError:  # local run: use the backend code from the repo, read-only
    sys.path.insert(0, os.environ.get("BACKEND_DIR", str(HERE.parents[1] / "backend")))
    from swarm.detect import detect, evaluate, parse_time
    from swarm.synthetic import generate

MAX_BYTES = 20 * 1024 * 1024   # keep in step with client_max_body_size in frontend/nginx.conf
MAX_ROWS = 200_000             # detect() is quadratic inside one time window
REQUIRED = ("id", "account", "timestamp", "text")
TRUE, FALSE = {"true", "1", "yes"}, {"false", "0", "no"}


def bad(message, status=400):
    raise HTTPException(status, message)


def parse_bool(value, column, line):
    v = value.strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    bad(f"line {line}: column '{column}' must be true or false, got '{value}'")


def parse_csv(raw):
    """CSV bytes -> list of posts in the backend's input format (docs/api.md)."""
    if not raw.strip():
        bad("The file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        bad("The file is not UTF-8 text. Save it as 'CSV UTF-8'.")
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") > header.count(",") else ","  # Excel in some locales
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        columns = [c.strip().lower() for c in next(reader)]
        missing = [c for c in REQUIRED if c not in columns]
        if missing:
            bad(f"Missing required column(s): {', '.join(missing)}. "
                f"The first line must be a header with at least: {', '.join(REQUIRED)}.")
        posts, seen = [], set()
        for cells in reader:
            line = reader.line_num
            if not any(c.strip() for c in cells):
                continue
            if len(cells) > len(columns):
                bad(f"line {line}: {len(cells)} values but the header has {len(columns)} "
                    "columns. Put text that contains the separator in double quotes.")
            row = dict(zip(columns, (c.strip() for c in cells)))
            for column in ("id", "account", "timestamp"):
                if not row.get(column):
                    bad(f"line {line}: '{column}' is empty.")
            try:
                parse_time(row["timestamp"])
            except ValueError:
                bad(f"line {line}: timestamp '{row['timestamp']}' is not ISO 8601 "
                    "(example: 2026-11-01T10:00:00Z).")
            if row["id"] in seen:
                bad(f"line {line}: id '{row['id']}' appears more than once.")
            seen.add(row["id"])
            post = {"id": row["id"], "account": row["account"],
                    "timestamp": row["timestamp"], "text": row.get("text") or ""}
            if row.get("links"):
                post["links"] = row["links"].replace("|", " ").split()
            if row.get("repost_of"):
                post["repost_of"] = row["repost_of"]
            # An empty 'coordinated' cell means "no label": the key must then be absent.
            if row.get("coordinated"):
                post["coordinated"] = parse_bool(row["coordinated"], "coordinated", line)
            if row.get("synthetic"):
                post["synthetic"] = parse_bool(row["synthetic"], "synthetic", line)
            posts.append(post)
            if len(posts) > MAX_ROWS:
                bad(f"Too many rows: the limit is {MAX_ROWS}.", 413)
    except csv.Error as e:
        bad(f"line {reader.line_num}: not valid CSV ({e}).")
    if not posts:
        bad("The file has a header but no rows.")
    return posts


class Dataset:
    def __init__(self, name, posts):
        self.posts = posts
        self.swarms = detect(posts)
        self.by_id = {s["id"]: s for s in self.swarms}
        self.source = {
            "name": name,
            "synthetic": any(p.get("synthetic") for p in posts),
            "posts": len(posts),
            "accounts": len({str(p["account"]) for p in posts}),
        }
        self.metrics = evaluate(posts, self.swarms)

    def listing(self):
        return {"source": self.source, "swarms": [
            {
                "id": s["id"], "size": s["size"], "edge_count": len(s["edges"]),
                "post_count": len(s["posts"]), "first_seen": s["first_seen"],
                "last_seen": s["last_seen"], "sample_text": s["posts"][0]["text"],
                "verdict": s["verdict"],
            }
            for s in self.swarms
        ]}


current = Dataset("synthetic sample", generate())
analyze_lock = threading.Lock()  # one analysis at a time: the VPS has 2 vCPUs

app = FastAPI(title="best_troll_catcher MOCK API (front-end owner's stand-in)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/swarms")
def list_swarms():
    return current.listing()


@app.get("/api/swarms/{swarm_id}")
def get_swarm(swarm_id: str):
    data = current
    if swarm_id not in data.by_id:
        raise HTTPException(404, "no such swarm")
    return data.by_id[swarm_id]


@app.get("/api/metrics")
def metrics():
    data = current
    return {"source": data.source, "metrics": data.metrics}


@app.post("/api/analyze")
def analyze(file: UploadFile = File(...)):
    """PROPOSED, not in docs/api.md yet. Returns the same shape as GET /api/swarms."""
    global current
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        bad(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    posts = parse_csv(raw)
    name = os.path.basename((file.filename or "").replace("\\", "/"))[:100] or "uploaded.csv"
    with analyze_lock:
        current = Dataset(name, posts)
        return current.listing()


# Local convenience only (no Docker, no nginx): serve the page from the same port.
# In the Docker image frontend/site does not exist and nginx serves it instead.
site = HERE.parent / "site"
if site.is_dir():
    app.mount("/samples", StaticFiles(directory=HERE / "samples"))
    app.mount("/", StaticFiles(directory=site, html=True))
