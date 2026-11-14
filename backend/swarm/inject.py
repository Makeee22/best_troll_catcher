"""Injection benchmark: plant simulated swarms in a background file and see what the detector finds.

    python -m swarm.inject COMMENTS [--out FILE] [--min-confidence X] [--similar-text] [--seed N]

The planted swarms are simulated; the background accounts are assumed not to be coordinated.
"""
import argparse
import csv
import json
import os
import random
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import timedelta

from . import synthetic
from .core import MIN_CONFIDENCE, analyze
from .load import InputError

PREFIX = "planted_"


@dataclass(frozen=True)
class Scenario:
    size: int = 8
    messages: int = 6
    own: int = 10
    participation: float = 1.0
    words: int = 15
    variant: str = "exact"


BASE = Scenario()
GRID = list(dict.fromkeys(
    [replace(BASE, size=n) for n in (3, 5, 8, 20, 50)]
    + [replace(BASE, messages=n) for n in (1, 2, 3, 6, 20)]
    + [replace(BASE, own=n) for n in (0, 10, 30, 100, 300)]
    + [replace(BASE, participation=p) for p in (1.0, 0.5, 0.25)]
    + [replace(BASE, variant=v) for v in ("exact", "edited", "reworded")]
    + [replace(BASE, messages=1, own=n) for n in (0, 2, 10)]
    + [replace(BASE, messages=1, own=2, words=7)]))


def plant(scenario, seed=0):
    """The planted rows (username, text, timestamp) for one scenario; the same for the same seed."""
    s = scenario
    rng = random.Random(f"{seed}:{s}")  # a str seed is stable across processes, unlike hash()
    members = [f"{PREFIX}{i}" for i in range(s.size)]
    message_words = sorted(synthetic.SYNONYMS) if s.variant == "reworded" else synthetic.WORDS
    replacements = sorted(set(synthetic.WORDS))
    seen, rows = set(), []

    def fresh(vocabulary, count):
        while True:  # never repeated, so nobody shares a random text by chance
            text = " ".join(rng.choices(vocabulary, k=count))
            if text not in seen:
                seen.add(text)
                return text

    def add(user, moment, text):
        rows.append({"username": user, "text": text, "timestamp": synthetic.iso(moment)})

    def copy(message):
        words = message.split()
        if s.variant == "edited":
            i = rng.randrange(len(words))
            words[i] = rng.choice([w for w in replacements if w != words[i]])
        elif s.variant == "reworded":
            for i in rng.sample(range(len(words)), min(3, len(words))):
                words[i] = synthetic.SYNONYMS[words[i]]
            j = rng.randrange(len(words) - 1)
            words[j], words[j + 1] = words[j + 1], words[j]
        return " ".join(words)

    for _ in range(s.messages):
        base = synthetic.START + timedelta(seconds=rng.uniform(0, synthetic.DAY))
        message = fresh(message_words, s.words)
        for member in rng.sample(members, max(2, round(s.size * s.participation))):
            add(member, base + timedelta(seconds=rng.uniform(0, 30)), copy(message))
    for member in members:
        for _ in range(s.own):
            moment = synthetic.START + timedelta(seconds=rng.uniform(0, synthetic.DAY))
            add(member, moment, fresh(synthetic.WORDS, rng.randint(6, 14)))
    return rows


def _header(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        fields = next(csv.reader(f), [])
    named = {}
    for name in fields:
        named.setdefault(name.strip().lower(), name)
    if "username" not in named or "text" not in named:
        raise InputError(f"{path}: the background needs a username and a text column")
    return fields, named


def _write_input(background, directory, fields, named, rows):
    path = os.path.join(directory, "comments.csv")
    shutil.copyfile(background, path)
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        for i, row in enumerate(rows):
            out = {named["username"]: row["username"], named["text"]: row["text"]}
            if "timestamp" in named:
                out[named["timestamp"]] = row["timestamp"]
            if "comment_id" in named:
                out[named["comment_id"]] = f"{PREFIX}row{i}"
            if "synthetic" in named:
                out[named["synthetic"]] = 1
            writer.writerow(out)
    return path


def _flagged(result):
    """Highest confidence per account in the reported clusters, and the cluster count."""
    found = {}
    for c in result["clusters"]:
        for a in c["accounts"]:
            found[a["username"]] = max(found.get(a["username"], 0), c["confidence"])
    return found, len(result["clusters"])


def run(comments_path, scenarios=GRID, seed=0, min_confidence=MIN_CONFIDENCE, **options):
    fields, named = _header(comments_path)
    print("baseline", file=sys.stderr)
    base = analyze(comments_path, min_confidence=min_confidence, **options)
    found, clusters = _flagged(base)
    out = {"background": {"comments_file": os.path.basename(comments_path), "accounts": base["source"]["accounts"],
                          "flagged": len(found), "clusters": clusters},
           "min_confidence": min_confidence, "options": options, "scenarios": []}
    for n, scenario in enumerate(scenarios, 1):
        print(f"scenario {n}/{len(scenarios)}", file=sys.stderr)
        row = asdict(scenario)
        try:
            with tempfile.TemporaryDirectory(prefix="swarm-inject-") as directory:
                path = _write_input(comments_path, directory, fields, named, plant(scenario, seed))
                found, clusters = _flagged(analyze(path, min_confidence=min_confidence, **options))
            planted = [u for u in found if u.startswith(PREFIX)]
            row.update(planted_flagged=len(planted),
                       confidence=max((found[u] for u in planted), default=None),
                       background_flagged=len(found) - len(planted), clusters=clusters)
        except InputError as e:
            row["error"] = str(e)
        out["scenarios"].append(row)
    return out


def _table(result):
    b = result["background"]
    lines = [f"background {b['comments_file']}: {b['accounts']} accounts, {b['flagged']} flagged in the baseline "
             f"(confidence >= {result['min_confidence']})",
             f"{'size':>4} {'msgs':>4} {'own':>4} {'part':>5} {'words':>5} {'variant':<8} {'found':>7} {'conf':>6} {'bg flagged':>10}"]
    for r in result["scenarios"]:
        head = f"{r['size']:>4} {r['messages']:>4} {r['own']:>4} {r['participation']:>5} {r['words']:>5} {r['variant']:<8}"
        if "error" in r:
            lines.append(f"{head} error: {r['error']}")
            continue
        conf = "-" if r["confidence"] is None else f"{r['confidence']:.3f}"
        found = f"{r['planted_flagged']}/{r['size']}"
        lines.append(f"{head} {found:>7} {conf:>6} {r['background_flagged']:>10}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m swarm.inject",
                                     description="Plant simulated swarms in a background file and tabulate what is found.")
    parser.add_argument("comments", help="background comments.csv")
    parser.add_argument("--out", help="write the full result as JSON to this file")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                        help=f"lowest confidence reported (default {MIN_CONFIDENCE})")
    parser.add_argument("--similar-text", action="store_true",
                        help="also link accounts that post reworded copies (needs pip install model2vec)")
    parser.add_argument("--similar-model", metavar="NAME", help="embedding model for --similar-text")
    parser.add_argument("--seed", type=int, default=0, help="seed for the planted swarms (default 0)")
    args = parser.parse_args(argv)
    options = {"similar_text": True} if args.similar_text else {}
    if args.similar_text and args.similar_model:
        options["similar_model"] = args.similar_model
    try:
        result = run(args.comments, GRID, args.seed, args.min_confidence, **options)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    print("\n".join(_table(result)))
    print("Planted swarms are simulated; the background accounts are assumed not to be coordinated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
