import csv
from collections import Counter
from swarm.synthetic import generate, write


def test_population():
    comments, profiles = generate()
    assert len(comments) == 5773
    assert all(c["synthetic"] == 1 for c in comments)
    assert Counter(p["label"] for p in profiles) == {"human": 240, "benign_feed": 3, "bot:swarm_0": 8, "bot:swarm_1": 5}
    assert {c["username"] for c in comments} == {p["username"] for p in profiles}


def test_same_seed_same_data():
    assert generate(3) == generate(3)
    assert generate(3) != generate(4)


def test_write_makes_two_readable_files(tmp_path):
    comments_path, profiles_path = write(str(tmp_path))
    with open(comments_path, newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 5773
    with open(profiles_path, newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 256
