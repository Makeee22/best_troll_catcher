"""HTTP API for the dashboard. The contract is docs/api.md: change both together.

    uvicorn swarm.api:app --reload              # synthetic sample data
    POSTS_FILE=posts.jsonl uvicorn swarm.api:app
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .detect import detect, evaluate, load_posts
from .synthetic import generate

posts_file = os.environ.get("POSTS_FILE")
posts = load_posts(posts_file) if posts_file else generate()
swarms = detect(posts)
by_id = {swarm["id"]: swarm for swarm in swarms}
source = {
    "name": os.path.basename(posts_file) if posts_file else "synthetic sample",
    "synthetic": any(post.get("synthetic") for post in posts),
    "posts": len(posts),
    "accounts": len({str(post["account"]) for post in posts}),
}

app = FastAPI(title="best_troll_catcher")
# Read-only public API: the dashboard may be served from another origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/swarms")
def list_swarms():
    summaries = [
        {
            "id": s["id"], "size": s["size"], "edge_count": len(s["edges"]),
            "post_count": len(s["posts"]), "first_seen": s["first_seen"],
            "last_seen": s["last_seen"], "sample_text": s["posts"][0]["text"],
            "verdict": s["verdict"],
        }
        for s in swarms
    ]
    return {"source": source, "swarms": summaries}


@app.get("/api/swarms/{swarm_id}")
def get_swarm(swarm_id: str):
    if swarm_id not in by_id:
        raise HTTPException(404, "no such swarm")
    return by_id[swarm_id]


@app.get("/api/metrics")
def metrics():
    return {"source": source, "metrics": evaluate(posts, swarms)}
