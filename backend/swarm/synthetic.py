"""Simulated comments and profiles in the standard format, with known swarms and innocent look-alikes.

Every comment carries synthetic = 1. Numbers measured on this data say that the
code works, not how good the detection is on real traffic. Anything shown to
others from this data must say that it is synthetic.

    python -m swarm.synthetic DIRECTORY    # write comments.csv and profiles.csv there
"""
import csv
import os
import random
import sys
from datetime import datetime, timedelta, timezone

WORDS = ("the city council voted on a new budget for schools and roads after long debate "
         "people in town say prices keep rising while wages stay flat this winter many "
         "families plan to travel less and cook at home more often than last year").split()
# Used only by the reworded swarm: a member swaps a few words for these.
SYNONYMS = {"city": "town", "council": "board", "voted": "decided", "new": "fresh", "budget": "spending",
            "schools": "classrooms", "roads": "streets", "long": "lengthy", "debate": "discussion",
            "people": "residents", "say": "claim", "prices": "costs", "keep": "continue", "rising": "climbing",
            "wages": "salaries", "stay": "remain", "flat": "stagnant", "families": "households",
            "plan": "intend", "travel": "journey", "cook": "prepare", "often": "frequently"}
DAY = 24 * 3600
START = datetime(2026, 11, 1, tzinfo=timezone.utc)
COMMENT_FIELDS = ["comment_id", "username", "timestamp", "text", "repost_of", "synthetic"]
PROFILE_FIELDS = ["username", "label", "created_at"]


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(seed=0, reworded=False):
    rng = random.Random(seed)
    comments, profiles = [], []
    seen = set()

    def add(username, seconds, text, repost_of=""):
        comments.append({
            "comment_id": f"syn{len(comments)}",
            "username": username,
            "timestamp": iso(START + timedelta(seconds=seconds)),
            "text": text,
            "repost_of": repost_of,
            "synthetic": 1,
        })

    def sentence():
        # never repeated, so two accounts cannot share a random sentence by chance
        while True:
            text = " ".join(rng.choices(WORDS, k=rng.randint(6, 14)))
            if text not in seen:
                seen.add(text)
                return text

    def spread(count):
        first, last = datetime(2023, 1, 1, tzinfo=timezone.utc), datetime(2025, 12, 31, tzinfo=timezone.utc)
        return [iso(first + (last - first) * i / (count - 1)) for i in range(count)]

    users = [f"user_{i:03d}" for i in range(200)]
    fans = [f"fan_{i:02d}" for i in range(40)]
    feeds = [f"newsfeed_{i}" for i in range(3)]
    ordinary = [(name, label) for names, label in ((users, "human"), (fans, "human"), (feeds, "benign_feed")) for name in names]
    for (name, label), created in zip(ordinary, spread(len(ordinary))):
        profiles.append({"username": name, "label": label, "created_at": created})

    for user in users:
        for _ in range(20):
            add(user, rng.uniform(0, DAY), sentence())

    # Innocent look-alikes that must not be flagged:
    # breaking news, shared once by many people within two minutes
    for user in rng.sample(users, 60):
        add(user, 40000 + rng.uniform(0, 120), "Breaking: bridge closed after storm https://news.example/bridge")
    # one viral post, reposted by many
    for user in rng.sample(users, 80):
        add(user, 60000 + rng.uniform(0, 600), "", "viral1")
    # a short greeting everyone uses
    for user in rng.sample(users, 50):
        add(user, rng.uniform(0, DAY), "good morning")

    # A fan community: chatty accounts that repost the same few celebrity posts.
    for fan in fans:
        for _ in range(30):
            add(fan, rng.uniform(0, DAY), sentence())
        for celeb in rng.sample(range(30), 4):
            add(fan, rng.uniform(0, DAY), "", f"celeb{celeb}")

    # Benign automated news feeds: they post the same wire headlines within seconds.
    # Timing and text reuse cannot tell them from a swarm, so the rules flag them.
    for i, headline in enumerate(sentence() for _ in range(5)):
        for feed in feeds:
            add(feed, 5000 + i * 15000 + rng.uniform(0, 20), f"WIRE: {headline}")

    # The swarms: every member posts each campaign message within 30 seconds,
    # aimed at a different user, between ordinary-looking posts of its own.
    for s, size in enumerate((8, 5)):
        members = [f"troll_{s}_{i}" for i in range(size)]
        created = datetime(2024, 3, 1, tzinfo=timezone.utc) + timedelta(days=rng.uniform(0, 400))
        for member in members:
            profiles.append({"username": member, "label": f"bot:swarm_{s}",
                             "created_at": iso(created + timedelta(days=rng.uniform(0, 10)))})
        for _ in range(6):
            base = rng.uniform(0, DAY)
            message = sentence()
            for member in members:
                add(member, base + rng.uniform(0, 30), f"@{rng.choice(users)} {message}")
        for member in members:
            for _ in range(10):
                add(member, rng.uniform(0, DAY), sentence())

    if reworded:
        # A swarm that rewords: every member posts each campaign message in its own wording,
        # so no two members post identical text and the exact-match signals find nothing.
        members = [f"troll_2_{i}" for i in range(6)]
        created = datetime(2024, 6, 1, tzinfo=timezone.utc) + timedelta(days=rng.uniform(0, 300))
        for member in members:
            profiles.append({"username": member, "label": "bot:reworded",
                             "created_at": iso(created + timedelta(days=rng.uniform(0, 10)))})
        for _ in range(6):
            base = rng.uniform(0, DAY)
            message = " ".join(rng.choices(sorted(SYNONYMS), k=rng.randint(8, 12)))
            for member in members:
                words = message.split()
                for i in rng.sample(range(len(words)), 3):
                    words[i] = SYNONYMS[words[i]]
                j = rng.randrange(len(words) - 1)
                words[j], words[j + 1] = words[j + 1], words[j]
                add(member, base + rng.uniform(0, 30), f"@{rng.choice(users)} " + " ".join(words))
        for member in members:
            for _ in range(10):
                add(member, rng.uniform(0, DAY), sentence())

    rng.shuffle(comments)
    return comments, profiles


def write(directory, seed=0, reworded=False):
    comments, profiles = generate(seed, reworded)
    os.makedirs(directory, exist_ok=True)
    paths = []
    for name, fields, rows in (("comments.csv", COMMENT_FIELDS, comments), ("profiles.csv", PROFILE_FIELDS, profiles)):
        path = os.path.join(directory, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return tuple(paths)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m swarm.synthetic DIRECTORY")
    print(*write(sys.argv[1]))
