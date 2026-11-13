"""Synthetic posts with known swarms, for testing detection before real data arrives.

Every post carries "synthetic": true. Numbers measured on this data say that the
code works, not how good the detection is on real traffic.

    python -m swarm.synthetic            # print the evaluation on this data
    python -m swarm.synthetic --dump     # print the posts as JSON Lines
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone

from .detect import detect, evaluate

WORDS = ("the city council voted on a new budget for schools and roads after long debate "
         "people in town say prices keep rising while wages stay flat this winter many "
         "families plan to travel less and cook at home more often than last year").split()
DAY = 24 * 3600


def generate(seed=0, organic=200, swarm_sizes=(8, 5), feeds=3):
    rng = random.Random(seed)
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    posts = []

    def add(account, seconds, text, coordinated, **extra):
        posts.append({
            "id": f"syn{len(posts)}",
            "account": account,
            "timestamp": (start + timedelta(seconds=seconds)).isoformat(),
            "text": text,
            "coordinated": coordinated,
            "synthetic": True,
            **extra,
        })

    def sentence():
        return " ".join(rng.choices(WORDS, k=rng.randint(6, 14)))

    users = [f"user_{i:03d}" for i in range(organic)]
    for user in users:
        for _ in range(20):
            add(user, rng.uniform(0, DAY), sentence(), False)

    # Innocent look-alikes that must not be flagged:
    # breaking news, shared once by many people within two minutes
    for user in rng.sample(users, 60):
        add(user, 40000 + rng.uniform(0, 120),
            "Breaking: bridge closed after storm https://news.example/bridge", False)
    # one viral post, reposted by many
    for user in rng.sample(users, 80):
        add(user, 60000 + rng.uniform(0, 600), "", False, repost_of="viral1")
    # a short greeting everyone uses
    for user in rng.sample(users, 50):
        add(user, rng.uniform(0, DAY), "good morning", False)

    # Benign automated news feeds: they post the same wire headlines within seconds.
    # Timing and text reuse cannot tell them from a swarm, so the rules flag them.
    headlines = [sentence() for _ in range(5)]
    for i, headline in enumerate(headlines):
        base = 5000 + i * 15000
        for n in range(feeds):
            add(f"newsfeed_{n}", base + rng.uniform(0, 20), f"WIRE: {headline}", False)

    # The swarms: every member posts each campaign message within 30 seconds,
    # aimed at a different user, between ordinary-looking posts of its own.
    for s, size in enumerate(swarm_sizes):
        members = [f"troll_{s}_{i}" for i in range(size)]
        for _ in range(6):
            base = rng.uniform(0, DAY)
            message = sentence()
            for member in members:
                add(member, base + rng.uniform(0, 30), f"@{rng.choice(users)} {message}", True)
        for member in members:
            for _ in range(10):
                add(member, rng.uniform(0, DAY), sentence(), True)

    rng.shuffle(posts)
    return posts


if __name__ == "__main__":
    posts = generate()
    if "--dump" in sys.argv:
        for post in posts:
            print(json.dumps(post))
    else:
        swarms = detect(posts)
        print(f"{len(posts)} synthetic posts, {len(swarms)} swarms found")
        for swarm in swarms:
            print(f"  {swarm['id']}  {swarm['size']} accounts  {swarm['accounts'][0]} ...")
        print(json.dumps(evaluate(posts, swarms), indent=2))
