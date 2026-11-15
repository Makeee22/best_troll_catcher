"""Turn a result.json of real data into one that may be published: no username, text, link, id or exact time.

    python examples/anonymise.py RESULT.json OUT.json --label "Cresci 2017 (research data, anonymised)" [--check COMMENTS.csv]

Kept: every number the core computed (sizes, confidences, copied shares, flags, edge counts and strengths, copy gaps,
creation-window counts, signals, diagnostics counts, metrics). Replaced: usernames by "account N" (the same number
everywhere in the file), shared items by "<kind> #N" placeholders with the text's word count, cluster ids by
"cluster-N", warnings by their count; times rounded down to the hour. --check scans the output for string: each
must be one of the known safe forms (placeholders, the core's keys and sentences, hour times, labels) and none may
equal a username or text of the source comments file; otherwise nothing is written.
"""
import argparse
import csv
import json
import re
import sys

PLACEHOLDER = {"text": "shared text #{n} ({w} words)", "similar_text": "group of reworded texts #{n} ({w} words)",
               "link": "shared link #{n}", "repost": "reposted post #{n}", "reply": "replied-to post #{n}"}


class Names:
    def __init__(self, prefix):
        self.prefix, self.seen = prefix, {}

    def __call__(self, value):
        if value is None:
            return None
        return self.seen.setdefault(value, f"{self.prefix} {len(self.seen) + 1}")


def _hour(ts):
    return re.sub(r"T(\d\d):\d\d:\d\dZ$", r"T\1:00:00Z", ts) if isinstance(ts, str) else ts


def anonymise(result, label):
    account, cluster_id, items = Names("account"), Names("cluster"), {}

    def item(kind, value):
        key = (kind, value)
        if key not in items:
            items[key] = PLACEHOLDER.get(kind, "item #{n}").format(n=len(items) + 1, w=len(str(value or "").split()))
        return items[key]

    out = dict(result)
    out["source"] = dict(result["source"], comments_file=label, profiles_file=label if result["source"].get("profiles_file") else None)
    out["warnings"] = [f"{len(result['warnings'])} input warnings (left out: they name the source files)"] if result["warnings"] else []
    out["clusters"] = []
    for c in result["clusters"]:
        c = dict(c, id=cluster_id(c["id"]).replace(" ", "-"), first_seen=_hour(c.get("first_seen")), last_seen=_hour(c.get("last_seen")))
        c["accounts"] = [dict(a, username=account(a["username"])) for a in c["accounts"]]
        c["edges"] = [dict(e, source=account(e["source"]), target=account(e["target"])) for e in c["edges"]]
        c["top_items"] = [dict(i, value=item(i["kind"], i["value"]), first_seen=_hour(i.get("first_seen")),
                               last_seen=_hour(i.get("last_seen"))) for i in c["top_items"]]
        out["clusters"].append(c)
    d = dict(result.get("diagnostics") or {})
    if d:
        d["widest_items"] = [dict(w, value=item(w["kind"], w["value"])) for w in d.get("widest_items") or []]
        if d.get("main_thread"):
            d["main_thread"] = dict(d["main_thread"], thread_id="thread 1", first_seen=_hour(d["main_thread"].get("first_seen")),
                                    last_seen=_hour(d["main_thread"].get("last_seen")))
        out["diagnostics"] = d
    out["collection"] = None
    return out


# every string the published file may hold: our placeholders, the core's own words and keys, times, labels
SAFE = re.compile(r"^(account \d+|cluster-\d+|thread 1|(shared text|group of reworded texts) #\d+ \(\d+ words\)|"
                  r"(shared link|reposted post|replied-to post|item) #\d+|\d{4}-\d\d-\d\dT\d\d:00:00Z|"
                  r"[a-z0-9_]+|(bot|human)(:[A-Za-z0-9_-]+)?|minishlab/[A-Za-z0-9_.-]+)$")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _keys(node):
    """Only the JSON keys: a username or text that leaked as a value must not be excused."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def check(out, comments_path, allowed):
    """Strings of the output that are not a known safe form, plus any that equal a source username or text."""
    strings = set(_strings(out))
    odd = {x for x in strings if not SAFE.match(x) and x not in allowed}
    with open(comments_path, newline="", encoding="utf-8") as f:
        hits = {v for row in csv.DictReader(f) for v in (row.get("username"), (row.get("text") or "").strip()) if v in strings}
    # a source text or name that is one of the file's own keys (a tweet saying just "confidence") identifies no one
    return odd, hits - set(_keys(out))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("result")
    p.add_argument("out")
    p.add_argument("--label", required=True)
    p.add_argument("--check", metavar="COMMENTS_CSV")
    a = p.parse_args(argv)
    with open(a.result, encoding="utf-8") as f:
        result = json.load(f)
    out = anonymise(result, a.label)
    if a.check:
        # the core's own sentences hold counts only; they and the label are allowed as written
        allowed = {a.label, *out["warnings"], *(r["text"] for r in (out.get("diagnostics") or {}).get("reasons") or []),
                   *(s for s in _strings(out.get("signals")) if isinstance(s, str))}
        odd, hits = check(out, a.check, allowed)
        if odd or hits:
            print(f"refused: {len(hits)} source values and {len(odd)} unexpected strings in the output", file=sys.stderr)
            for x in sorted(odd)[:20]:
                print("  unexpected:", x[:40] + ("…" if len(x) > 40 else ""), file=sys.stderr)
            return 1
    text = json.dumps(out, ensure_ascii=False, indent=1)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
