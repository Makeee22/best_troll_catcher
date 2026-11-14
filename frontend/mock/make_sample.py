"""Write samples/synthetic_sample.csv from the backend's synthetic generator.

    python make_sample.py        # run from frontend/mock/

Every row is simulated and says so in its 'synthetic' column.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
from swarm.synthetic import generate  # noqa: E402

COLUMNS = ("id", "account", "timestamp", "text", "links", "repost_of", "coordinated", "synthetic")

with open(HERE / "samples" / "synthetic_sample.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f, lineterminator="\n")
    writer.writerow(COLUMNS)
    for post in generate():
        writer.writerow([
            post["id"], post["account"], post["timestamp"], post["text"],
            " ".join(post.get("links") or []), post.get("repost_of") or "",
            "true" if post["coordinated"] else "false", "true",
        ])
