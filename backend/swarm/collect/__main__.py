import argparse
import http.client
import json
import os
import sys

from ..convert import ConvertError
from ..core import MIN_CONFIDENCE
from ..load import InputError
from . import CollectError, analyse, collect


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m swarm.collect",
                                     description="Fetch a discussion from a link, then convert and analyse it.")
    parser.add_argument("url", help="a link to a discussion (see docs/collect-interface.md for the supported sites)")
    parser.add_argument("out_dir", help="directory for bundle.json, comments.csv, profiles.csv and result.json")
    parser.add_argument("--history", type=int, default=25, help="newest posts fetched per commenter (default 25)")
    parser.add_argument("--max-participants", type=int, default=150,
                        help="commenters whose history is fetched (default 150); the rest are judged on their thread posts")
    parser.add_argument("--no-similar-text", action="store_true", help="skip the reworded-copies signal")
    args = parser.parse_args(argv)
    try:
        os.makedirs(args.out_dir, exist_ok=True)
        bundle = collect(args.url, history=args.history, max_participants=args.max_participants,
                         on_progress=lambda done, total: print(f"\rhistories {done}/{total}", end="", file=sys.stderr, flush=True))
        print(file=sys.stderr)
        with open(os.path.join(args.out_dir, "bundle.json"), "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=1)
        result = analyse(bundle, args.out_dir, similar_text=not args.no_similar_text)
        with open(os.path.join(args.out_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except (CollectError, ConvertError, InputError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (http.client.HTTPException, ValueError) as e:   # a bad answer that got past the client: still one line
        print(f"error: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return 2
    except RecursionError:
        print("error: this thread is nested too deeply to save", file=sys.stderr)
        return 2

    for w in result["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    source, thread = result["source"], bundle["thread"]
    print(f"{thread['platform']}: {source['comments']} comments from {source['accounts']} accounts, "
          f"{bundle['credits_used']} credits used")
    for kind, s in result["signals"].items():
        detail = f"{s['items']} items, {s['links']} links" if s["status"] == "used" else s["reason"]
        print(f"signal {kind}: {s['status']} ({detail})")
    clusters = result["clusters"]
    print(f"{len(clusters)} clusters at confidence >= {MIN_CONFIDENCE}")
    for c in clusters:
        print(f"  {c['id']}  size {c['size']}  confidence {c['confidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
