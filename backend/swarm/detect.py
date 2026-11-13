"""Find groups of accounts that repeatedly post the same content within seconds of each other.

One shared post proves nothing (breaking news, a viral post), so two accounts are
linked only after they co-post on several separate occasions.
"""
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

# Detection criteria. The data owner tunes these; docs/criteria.md explains them.
WINDOW_SECONDS = 60  # two posts count as simultaneous within this gap
MIN_SHARED = 3       # a pair must co-post on this many separate occasions to be linked
MIN_SIZE = 3         # smallest group reported as a swarm
MIN_WORDS = 5        # shorter texts ("good morning") are reused innocently

URL = re.compile(r"https?://\S+")


def load_posts(path):
    """Read posts from a JSON Lines file (format: docs/api.md)."""
    posts = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            post = json.loads(line)
            for field in ("id", "account", "timestamp"):
                if field not in post:
                    raise ValueError(f"{path}:{n}: missing field '{field}'")
            posts.append(post)
    return posts


def parse_time(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.timestamp()


def normalise(text):
    """Lower-case words only, without URLs and @mentions, so small edits don't hide a copy."""
    text = URL.sub(" ", text.lower())
    text = re.sub(r"@\w+", " ", text)
    return " ".join(re.findall(r"\w+", text))


def content_keys(post):
    """What a post shares with its copies: its text, its links, the post it reposts."""
    text = post.get("text") or ""
    keys = []
    words = normalise(text)
    if len(words.split()) >= MIN_WORDS:
        keys.append(("text", words))
    for url in set(post.get("links") or URL.findall(text)):
        keys.append(("link", url.rstrip(".,)")))
    if post.get("repost_of"):
        keys.append(("repost", str(post["repost_of"])))
    return keys


def detect(posts, window=WINDOW_SECONDS, min_shared=MIN_SHARED, min_size=MIN_SIZE):
    """Return the swarms found in posts, largest first."""
    by_id = {str(p["id"]): p for p in posts}
    by_key = defaultdict(list)
    for post in posts:
        t = parse_time(post["timestamp"])
        for key in content_keys(post):
            by_key[key].append((t, str(post["account"]), str(post["id"])))

    # For every pair of accounts: which posts of each took part in a simultaneous copy.
    # shortcut: quadratic inside one time window, fine up to ~100k posts; bucket by time beyond that
    pair_posts = defaultdict(lambda: (set(), set()))
    for items in by_key.values():
        items.sort()
        for i, (t1, a1, id1) in enumerate(items):
            for j in range(i + 1, len(items)):
                t2, a2, id2 = items[j]
                if t2 - t1 > window:
                    break
                if a1 == a2:
                    continue
                (x, idx), (y, idy) = sorted([(a1, id1), (a2, id2)])
                first, second = pair_posts[(x, y)]
                first.add(idx)
                second.add(idy)

    # A post with the same text and link as another is one occasion, not two, and one
    # account repeating itself is one occasion too: count the less active side's posts.
    edges = {pair: min(len(a), len(b)) for pair, (a, b) in pair_posts.items()}
    edges = {pair: n for pair, n in edges.items() if n >= min_shared}

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)

    groups = defaultdict(list)
    for pair in edges:
        groups[find(pair[0])].append(pair)

    swarms = []
    for pairs in groups.values():
        accounts = sorted({account for pair in pairs for account in pair})
        if len(accounts) < min_size:
            continue
        post_ids = set()
        for pair in pairs:
            post_ids |= pair_posts[pair][0] | pair_posts[pair][1]
        evidence = sorted((by_id[i] for i in post_ids), key=lambda p: parse_time(p["timestamp"]))
        swarms.append({
            "id": hashlib.sha1(",".join(accounts).encode()).hexdigest()[:10],
            "size": len(accounts),
            "accounts": accounts,
            "edges": [{"source": a, "target": b, "shared": edges[(a, b)]} for a, b in sorted(pairs)],
            "first_seen": evidence[0]["timestamp"],
            "last_seen": evidence[-1]["timestamp"],
            "posts": [
                {"id": str(p["id"]), "account": str(p["account"]),
                 "timestamp": p["timestamp"], "text": p.get("text") or ""}
                for p in evidence
            ],
            "verdict": None,  # filled by the decision model once it exists
        })
    return sorted(swarms, key=lambda s: (-s["size"], s["id"]))


def evaluate(posts, swarms):
    """Account-level precision, recall and false-positive rate, or None without labels.

    An account counts as coordinated if any of its posts has "coordinated": true.
    """
    truth = {}
    for post in posts:
        if "coordinated" in post:
            account = str(post["account"])
            truth[account] = truth.get(account, False) or bool(post["coordinated"])
    if not truth:
        return None
    flagged = {account for swarm in swarms for account in swarm["accounts"]}
    tp = sum(1 for a, bad in truth.items() if bad and a in flagged)
    fp = sum(1 for a, bad in truth.items() if not bad and a in flagged)
    fn = sum(1 for a, bad in truth.items() if bad and a not in flagged)
    tn = len(truth) - tp - fp - fn

    def ratio(part, whole):
        return round(part / whole, 4) if whole else None

    return {
        "labelled_accounts": len(truth),
        "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "true_negatives": tn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
    }
