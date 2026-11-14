import argparse
import json
import sys

from .core import MIN_CONFIDENCE, analyze
from .load import InputError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m swarm",
                                     description="Find groups of accounts that behave like one actor.")
    parser.add_argument("comments", help="comments.csv")
    parser.add_argument("--profiles", help="profiles.csv (optional)")
    parser.add_argument("--out", help="write the full result as JSON to this file")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                        help=f"lowest confidence reported (default {MIN_CONFIDENCE})")
    parser.add_argument("--similar-text", action="store_true",
                        help="also link accounts that post reworded copies (needs pip install model2vec)")
    parser.add_argument("--ignore", metavar="FILE",
                        help="file of usernames to leave out, one per line (known feeds, staff accounts)")
    args = parser.parse_args(argv)
    try:
        result = analyze(args.comments, args.profiles, min_confidence=args.min_confidence,
                         similar_text=args.similar_text, ignore_path=args.ignore)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for w in result["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)

    source = result["source"]
    if source["synthetic"]:
        print("NOTE: this data is synthetic; the numbers show the code works, not how good detection is.")
    print(f"{source['comments']} comments from {source['accounts']} accounts")
    for kind, s in result["signals"].items():
        detail = f"{s['items']} items, {s['links']} links" if s["status"] == "used" else s["reason"]
        print(f"signal {kind}: {s['status']} ({detail})")
    clusters = result["clusters"]
    print(f"{len(clusters)} clusters at confidence >= {args.min_confidence}")
    for c in clusters:
        print(f"  {c['id']}  size {c['size']}  confidence {c['confidence']}")
    metrics = result["metrics"]
    if metrics:
        m = metrics["at_min_confidence"]
        print(f"precision {m['precision']}  recall {m['recall']}  false-positive rate {m['false_positive_rate']}"
              f"  (at confidence >= {args.min_confidence})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
