"""Read-only HTTP API serving one result, fixed at startup. The contract is docs/api.md: change both together.

    uvicorn swarm.api:app --reload                                    # synthetic sample
    RESULT_FILE=result.json uvicorn swarm.api:app                     # a result from the command line
    COMMENTS_FILE=c.csv [PROFILES_FILE=p.csv] uvicorn swarm.api:app   # analysed at startup
"""
import json
import os
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .core import analyze
from .load import InputError
from .synthetic import write


def _load_result():
    result_file = os.environ.get("RESULT_FILE") or None
    comments_file = os.environ.get("COMMENTS_FILE") or None
    profiles_file = os.environ.get("PROFILES_FILE") or None
    if result_file:
        try:
            with open(result_file, encoding="utf-8") as f:
                result = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit(f"RESULT_FILE {result_file} cannot be read as JSON: {e}") from None
        if not isinstance(result, dict) or not all(k in result for k in ("source", "parameters", "signals", "warnings", "clusters")):
            raise SystemExit(f"RESULT_FILE {result_file} is not a result written by `python -m swarm`")
        return result
    if comments_file:
        try:
            return analyze(comments_file, profiles_file)
        except InputError as e:
            raise SystemExit(f"COMMENTS_FILE cannot be analysed: {e}") from None
    with tempfile.TemporaryDirectory(prefix="swarm-sample-") as work:
        return analyze(*write(work))


result = _load_result()
by_id = {c["id"]: c for c in result["clusters"]}

app = FastAPI(title="best_troll_catcher")
# Read-only public API: the dashboard may be served from another origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/swarms")
def list_swarms():
    swarms = [
        {"id": c["id"], "size": c["size"], "confidence": c["confidence"], "edge_count": c["edge_count"],
         "first_seen": c["first_seen"], "last_seen": c["last_seen"],
         "sample": c["top_items"][0] if c["top_items"] else None, "declared_automation": c["declared_automation"]}
        for c in result["clusters"]
    ]
    return {"source": result["source"], "parameters": result["parameters"], "signals": result["signals"],
            "warnings": result["warnings"], "swarms": swarms}


@app.get("/api/swarms/{swarm_id}")
def get_swarm(swarm_id: str):
    if swarm_id not in by_id:
        raise HTTPException(404, "no such swarm")
    return by_id[swarm_id]


@app.get("/api/metrics")
def metrics():
    return {"source": result["source"], "metrics": result["metrics"]}
