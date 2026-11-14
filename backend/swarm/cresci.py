"""Convert the Cresci 2017 zips to the standard comments.csv and profiles.csv."""
import csv
import io
import os
import re
import sys
import zipfile
from datetime import datetime, timezone

SETS = [("genuine_accounts", "human"),
        ("social_spambots_1", "bot:social_1"),
        ("social_spambots_2", "bot:social_2"),
        ("social_spambots_3", "bot:social_3"),
        ("traditional_spambots_1", "bot:traditional_1"),
        ("fake_followers", "bot:fake_followers")]
COMMENT_COLUMNS = ["comment_id", "username", "timestamp", "text", "parent_id", "repost_of", "likes", "client"]
PROFILE_COLUMNS = ["username", "label", "created_at", "followers", "following", "post_count", "default_avatar", "verified"]
TIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%a %b %d %H:%M:%S %z %Y"]
NO_VALUE = {"", "NULL", "\\N", "0"}
TAGS = re.compile(r"<[^>]*>")


def rows(z, name):
    """Stream one CSV member of the zip; None if the member is missing."""
    try:
        raw = z.open(name)
    except KeyError:
        return None
    text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
    return csv.DictReader(line.replace("\0", "") for line in text)


def ident(value):
    value = (value or "").strip()
    return "" if value in NO_VALUE else value


def count(value):
    value = (value or "").strip()
    return value if value.isdigit() else ""


def flag(value):
    return "1" if (value or "").strip().lower() in ("1", "true") else "0"


def utc(value):
    value = (value or "").strip()
    for fmt in TIME_FORMATS:
        try:
            t = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if t.tzinfo:
            t = t.astimezone(timezone.utc)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def convert_set(src, name, label, comments, profiles):
    path = os.path.join(src, f"{name}.csv.zip")
    if not os.path.exists(path):
        print(f"skipped {name}: {path} not found")
        return
    n_users = n_tweets = 0
    with zipfile.ZipFile(path) as z:
        for u in rows(z, f"{name}.csv/users.csv") or []:
            username = ident(u.get("id"))
            if not username:
                continue
            # fake_followers has no users.timestamp, only a created_at in Twitter's format
            created = utc(u.get("timestamp")) or utc(u.get("created_at"))
            profiles.writerow([username, label, created, count(u.get("followers_count")),
                               count(u.get("friends_count")), count(u.get("statuses_count")),
                               flag(u.get("default_profile_image")), flag(u.get("verified"))])
            n_users += 1
        for t in rows(z, f"{name}.csv/tweets.csv") or []:
            username, stamp = ident(t.get("user_id")), utc(t.get("timestamp"))
            if not username or not stamp:
                continue
            comments.writerow([ident(t.get("id")), username, stamp, t.get("text") or "",
                               ident(t.get("in_reply_to_status_id")), ident(t.get("retweeted_status_id")),
                               count(t.get("favorite_count")), TAGS.sub("", t.get("source") or "").strip()])
            n_tweets += 1
    print(f"{name}: {n_users} profiles, {n_tweets} comments")


def convert(source_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    csv.field_size_limit(10**9)
    with open(os.path.join(out_dir, "comments.csv"), "w", newline="", encoding="utf-8") as cf, \
            open(os.path.join(out_dir, "profiles.csv"), "w", newline="", encoding="utf-8") as pf:
        comments, profiles = csv.writer(cf), csv.writer(pf)
        comments.writerow(COMMENT_COLUMNS)
        profiles.writerow(PROFILE_COLUMNS)
        for name, label in SETS:
            convert_set(source_dir, name, label, comments, profiles)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m swarm.cresci SOURCE_DIR OUT_DIR")
    convert(sys.argv[1], sys.argv[2])
