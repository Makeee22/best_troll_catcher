"""Turn a raw bundle (JSON) or a saved .html page into comments.csv and profiles.csv."""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

from . import schemaorg, sites

COMMENT_COLUMNS = ["comment_id", "username", "text", "timestamp", "parent_id", "thread_id"]
PROFILE_COLUMNS = ["username", "display_name", "created_at", "post_count"]
ANONYMOUS = {"", "[deleted]", "[removed]", "deleted", "automoderator", "nimetön", "anonyymi", "anonymous", "guest"}
ANONYMOUS_PREFIX = re.compile(r"^(verified user|a google user|anonymous|guest)\b")
SAME_COMMENT_SECONDS = 120


class ConvertError(ValueError):
    pass


def iso_utc(value):
    """A time in any form we know as 2026-11-14T10:00:00Z, or '' when it is not a time."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            dt = datetime.fromtimestamp(value, timezone.utc)
        else:
            dt = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_anonymous(name):
    name = (name or "").strip().casefold()
    return name in ANONYMOUS or bool(ANONYMOUS_PREFIX.match(name))


def _bare(cid):
    return re.sub(r"^t[13]_", "", str(cid or ""))  # ids may arrive as numbers


def _key(r):
    return r["username"].casefold(), " ".join(r["text"].split()).casefold()


def _seconds(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else None


def _same_comment(a, b, lone):
    sa, sb = _seconds(a["timestamp"]), _seconds(b["timestamp"])
    if sa is None or sb is None:
        return lone
    return abs(sa - sb) <= SAME_COMMENT_SECONDS


def _merge_profiles(profiles):
    merged = {}
    for p in profiles:
        into = merged.setdefault(p["username"].casefold(), dict.fromkeys(PROFILE_COLUMNS, ""))
        for k in PROFILE_COLUMNS:
            value = iso_utc(p.get(k)) if k == "created_at" else str(p.get(k) or "")
            into[k] = into[k] or value
    return list(merged.values())


def merge(rows, profiles):
    """One comment per real comment: placeholders and empty texts dropped, history copies of thread comments joined."""
    warnings, kept, anonymous, empty = [], [], 0, 0
    for r in rows:
        r = dict(r, comment_id=_bare(r.get("comment_id")), parent_id=_bare(r.get("parent_id")),
                 username=str(r.get("username") or ""), text=str(r.get("text") or ""),
                 timestamp=iso_utc(r.get("timestamp")))
        if is_anonymous(r["username"]):
            anonymous += 1
        elif not r["text"].strip():
            empty += 1
        else:
            kept.append(r)
    if anonymous:
        warnings.append(f"converter: left out {anonymous} comment{'' if anonymous == 1 else 's'} by an anonymous or placeholder author")
    if empty:
        warnings.append(f"converter: left out {empty} without text")

    kept.sort(key=lambda r: r.get("source") == "history")  # stable: thread rows first
    seen, unique = set(), []
    for r in kept:
        if r["comment_id"] and r["comment_id"] in seen:
            continue
        seen.add(r["comment_id"])
        unique.append(r)

    threads, pending = {}, Counter(_key(r) for r in unique if r.get("source") == "history")
    alias, comments = {}, []
    for r in unique:
        if r.get("source") != "history":
            threads.setdefault(_key(r), []).append(r)
            comments.append(r)
            continue
        cands = threads.get(_key(r), [])
        lone = len(cands) == 1 and pending[_key(r)] == 1
        twin = next((t for t in cands if _same_comment(r, t, lone)), None)
        if twin:
            if r["comment_id"]:  # an alias under "" would rewrite every root comment's empty parent_id
                alias[r["comment_id"]] = twin["comment_id"]
        else:
            comments.append(r)
    for r in comments:
        r["parent_id"] = alias.get(r["parent_id"], r["parent_id"])
    # display_name lives on comment rows; the core reads it from profiles
    named = [{"username": r["username"], "display_name": r["display_name"]} for r in comments if r.get("display_name")]
    return comments, _merge_profiles(profiles + named), warnings


def _read_source(src, page_url):
    """parsed output first, then site rules on the html, then schema.org markup."""
    url = src.get("url") or page_url
    rows, profiles, notes = sites.from_parsed(src["parsed"], url) if src.get("parsed") else ([], [], [])
    if not rows and src.get("html"):
        more_rows, more_profiles, more_notes = sites.from_html(src["html"], url)
        rows = more_rows or schemaorg.from_html(src["html"], url)
        profiles, notes = profiles + more_profiles, notes + more_notes
    return rows, profiles, notes


def _history_rows(histories):
    rows, profiles = [], []
    for h in histories:
        if h.get("status") == "failed":
            continue
        user = str(h.get("username") or "")
        for i in h.get("items") or []:
            rows.append({"comment_id": i.get("id"), "username": user, "display_name": "", "text": i.get("text"),
                         "timestamp": i.get("timestamp"), "parent_id": i.get("parent_id"),
                         "thread_id": i.get("thread_id"), "source": "history"})
        if h.get("created_at"):
            profiles.append({"username": user, "display_name": "", "created_at": h["created_at"], "post_count": ""})
    return rows, profiles


def convert(bundle):
    url = bundle.get("url") or ""
    rows, profiles, notes = [], [], list((bundle.get("coverage") or {}).get("notes") or [])
    for page in bundle.get("pages") or []:
        for src in [page, *(page.get("frames") or [])]:
            r, p, n = _read_source(src, page.get("url") or url)
            rows += r
            profiles += p
            notes += n
    hr, hp = _history_rows(bundle.get("histories") or [])
    rows = [dict(r, source=r.get("source") or "thread") for r in rows] + hr
    comments, profiles, warnings = merge(rows, profiles + hp)
    if not comments:
        raise ConvertError(f"no comments found in {url}" + "".join(f"; {w}" for w in warnings))
    return comments, profiles, notes + warnings


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load(path):
    with open(path, encoding="utf-8") as f:
        if path.lower().endswith((".html", ".htm")):
            return {"url": path, "pages": [{"url": path, "role": "thread", "html": f.read()}]}
        bundle = json.load(f)
    if not isinstance(bundle, dict):
        raise ConvertError(f"{path} is not a raw bundle (a JSON object)")
    return bundle


def write(bundle_or_path, out_dir):
    bundle = _load(bundle_or_path) if isinstance(bundle_or_path, str) else bundle_or_path
    comments, profiles, warnings = convert(bundle)
    os.makedirs(out_dir, exist_ok=True)
    comments_path = os.path.join(out_dir, "comments.csv")
    _write_csv(comments_path, COMMENT_COLUMNS, comments)
    profiles_path = os.path.join(out_dir, "profiles.csv") if profiles else None
    if profiles_path:
        _write_csv(profiles_path, PROFILE_COLUMNS, profiles)
    return comments_path, profiles_path, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m swarm.convert",
                                     description="Turn a raw bundle (.json) or a saved page (.html) into comments.csv and profiles.csv.")
    parser.add_argument("input", help="bundle .json or saved .html page")
    parser.add_argument("out_dir", help="directory for comments.csv and profiles.csv")
    args = parser.parse_args(argv)
    try:
        comments_path, profiles_path, warnings = write(args.input, args.out_dir)
    except (ValueError, OSError) as e:  # ConvertError, bad JSON and bad encoding are ValueErrors
        print(f"error: {e}", file=sys.stderr)
        return 2
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    with open(comments_path, encoding="utf-8") as f:
        n = sum(1 for _ in csv.reader(f)) - 1
    print(f"{n} comments -> {comments_path}")
    if profiles_path:
        print(f"profiles -> {profiles_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
