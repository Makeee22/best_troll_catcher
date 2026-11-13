from swarm.detect import detect, evaluate, normalise
from swarm.synthetic import generate


def test_finds_swarms_and_spares_ordinary_users():
    posts = generate()
    flagged = {account for swarm in detect(posts) for account in swarm["accounts"]}
    trolls = {p["account"] for p in posts if p["coordinated"]}
    assert trolls <= flagged
    # breaking news, a viral repost and a common greeting must not link ordinary users
    assert not any(account.startswith("user_") for account in flagged)


def test_same_text_and_link_in_one_post_is_one_occasion():
    posts = [
        {"id": f"{a}{n}", "account": a, "timestamp": f"2026-11-01T10:0{n}:00Z",
         "text": f"read this now everyone please number {n} https://x.example/{n}"}
        for a in "abc" for n in range(2)
    ]
    assert detect(posts) == []          # two occasions, below MIN_SHARED = 3
    assert len(detect(posts, min_shared=2)) == 1


def test_normalise_ignores_mentions_links_and_case():
    assert normalise("@bob Look HERE: https://x.example/1!") == "look here"


def test_evaluate_without_labels_is_none():
    assert evaluate([{"id": 1, "account": "a", "timestamp": "2026-11-01T00:00:00Z"}], []) is None
