import json

import pytest
from swarm.core import analyze
from swarm.load import InputError
from swarm.synthetic import write


def test_result_document(tmp_path):
    result = analyze(*write(str(tmp_path)))
    json.dumps(result)
    assert result["source"] == {"comments_file": "comments.csv", "profiles_file": "profiles.csv",
                                "comments": 5773, "accounts": 256, "synthetic": True}
    assert result["parameters"] == {"min_words": 5, "min_shared": 2, "long_words": 10, "alpha": 0.01, "min_size": 3,
                                    "min_confidence": 0.2, "member_ratio": 0.5, "created_days": 30, "group_loose": 0.05, "rate_cap": 10}
    assert [c["size"] for c in result["clusters"]] == [3, 8, 5]            # feeds at 1.0, then the swarms
    assert result["metrics"]["at_min_confidence"]["precision"] == 0.8125
    swarm = result["clusters"][1]
    assert set(swarm) == {"id", "size", "confidence", "accounts", "edge_count", "edges", "top_items",
                          "first_seen", "last_seen", "created_within_30_days", "copy_gap_seconds", "declared_automation",
                          "flagged_members"}
    assert swarm["confidence"] == 0.375 and swarm["edge_count"] == 28 and len(swarm["edges"]) == 28
    assert swarm["accounts"][0] == {"username": "troll_0_0", "copied_share": 0.375, "flagged": True}
    assert swarm["flagged_members"] == swarm["size"]
    assert swarm["edges"][0].keys() == {"source", "target", "kind", "shared", "created_together"}
    assert len(swarm["top_items"]) == 6 and swarm["top_items"][0]["accounts"] == 8
    assert swarm["top_items"][0]["kind"] == "text" and swarm["top_items"][0]["first_seen"].endswith("Z")
    assert swarm["created_within_30_days"] == {"accounts": 8, "of": 8}
    assert result["clusters"][0]["declared_automation"] == {"accounts": 3, "of": 3}    # newsfeed_0..2
    assert swarm["declared_automation"] is None and result["clusters"][2]["declared_automation"] is None


def _trio_profiles(tmp_path, make_csv, names, bios):
    rows = [{"username": u, "text": f"the plan for item {i} is ready for everyone now"} for i in range(4) for u in names]
    rows += [{"username": u, "text": f"{u} wrote note number {i} about the weather today"}
             for u in names + [f"bg{k}" for k in range(50)] for i in range(10)]
    profiles = [{"username": u, "bio": b} for u, b in zip(names, bios)]
    return analyze(make_csv(tmp_path, "c.csv", rows), make_csv(tmp_path, "p.csv", profiles), min_confidence=0)


def test_a_swarm_posing_as_a_feed_is_marked_but_still_reported_unchanged(tmp_path, make_csv):
    plain = _trio_profiles(tmp_path, make_csv, ["a", "b", "c"], ["", "", ""])
    posing = _trio_profiles(tmp_path, make_csv, ["a", "b", "c"], ["Automated news feed", "a bot", ""])
    strip = lambda r: [{k: v for k, v in c.items() if k != "declared_automation"} for c in r["clusters"]]
    assert strip(posing) == strip(plain) and len(plain["clusters"]) == 1
    assert plain["clusters"][0]["declared_automation"] is None
    assert posing["clusters"][0]["declared_automation"] == {"accounts": 2, "of": 3}


def test_denying_or_feeding_is_not_declaring(tmp_path, make_csv):
    result = _trio_profiles(tmp_path, make_csv, ["notabot1", "talk_feedback", "cat_lady"],
                            ["I am NOT a bot", "real person, no bots here", "I feed stray cats"])
    assert result["clusters"][0]["declared_automation"] is None


def test_ignore_list_leaves_accounts_out(tmp_path):
    paths = write(str(tmp_path))
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("# known feeds\n\n  newsfeed_0 \nnewsfeed_1\nnewsfeed_2\nno_such_user\n", encoding="utf-8")
    before = analyze(*paths)
    result = analyze(*paths, ignore_path=str(ignore))
    accounts = lambda r: sorted(sorted(a["username"] for a in c["accounts"]) for c in r["clusters"])
    assert accounts(result) == [a for a in accounts(before) if not a[0].startswith("newsfeed_")]
    assert not any(a["username"].startswith("newsfeed_") for c in result["clusters"] for a in c["accounts"])
    assert result["parameters"]["ignored_accounts"] == 3 and "ignored_accounts" not in before["parameters"]
    assert result["source"]["accounts"] == before["source"]["accounts"] - 3
    assert any(w.startswith("ignore list: left out 3 accounts (") and w.endswith(" comments)") for w in result["warnings"])
    assert "ignore list: 1 names match no account" in result["warnings"]


def test_ignore_list_that_removes_everything_is_an_input_error(tmp_path, make_csv):
    comments = make_csv(tmp_path, "c.csv", [{"username": "a", "text": "one two three four five six"}])
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("a\n", encoding="utf-8")
    with pytest.raises(InputError, match="leaves no comments"):
        analyze(comments, ignore_path=str(ignore))
    with pytest.raises(InputError, match="cannot read the ignore list"):
        analyze(comments, ignore_path=str(tmp_path / "nope.txt"))


def _copy_rows(with_times):
    """Three accounts copy two texts: the first one 10 s apart, the second 30 s apart."""
    rows = []
    for text, start, step in (("the plan for the first item is ready now", 36000, 10),
                              ("the plan for the second item is ready now", 43200, 30)):
        for k, user in enumerate(("s0", "s1", "s2")):
            t = start + k * step
            row = {"username": user, "text": text}
            if with_times:
                row["timestamp"] = f"2026-11-01T{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}Z"
            rows.append(row)
    return rows + [{"username": f"bg{a}", "text": f"bg{a} wrote note number {i} about today"}
                   for a in range(30) for i in range(3)]


def test_copy_gap_is_the_median_time_between_copies(tmp_path, make_csv):
    result = analyze(make_csv(tmp_path, "c.csv", _copy_rows(True)), min_confidence=0)
    assert [a["username"] for a in result["clusters"][0]["accounts"]] == ["s0", "s1", "s2"]
    assert result["clusters"][0]["copy_gap_seconds"] == {"median": 20.0, "items": 2}   # gaps of 10 s and 30 s


def test_copy_gap_is_null_without_timestamps(tmp_path, make_csv):
    result = analyze(make_csv(tmp_path, "c.csv", _copy_rows(False)), min_confidence=0)
    assert len(result["clusters"]) == 1 and result["clusters"][0]["copy_gap_seconds"] is None


def test_without_profiles(tmp_path):
    comments, _ = write(str(tmp_path))
    result = analyze(comments)
    assert result["metrics"] is None and result["source"]["profiles_file"] is None
    assert result["clusters"][0]["created_within_30_days"] is None


def test_min_confidence_cuts_the_list(tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    assert [c["size"] for c in result["clusters"]] == [3]
    assert result["parameters"]["min_confidence"] == 0.5


def test_same_input_same_output(tmp_path):
    paths = write(str(tmp_path))
    assert json.dumps(analyze(*paths), sort_keys=True) == json.dumps(analyze(*paths), sort_keys=True)


def test_analyze_removes_its_temporary_database(tmp_path):
    import glob, tempfile
    before = set(glob.glob(f"{tempfile.gettempdir()}/swarm-*"))
    analyze(*write(str(tmp_path)))
    assert set(glob.glob(f"{tempfile.gettempdir()}/swarm-*")) == before


def test_a_member_that_copies_far_less_than_its_cluster_is_linked_not_flagged(tmp_path, make_csv):
    # the Cresci subset trap: a few links bridge a real account into a swarm; it must not inherit the swarm's confidence
    from test_detect import background, shared, unique
    rows = shared("abc", 6) + shared("ad", 2, tag="other") + unique("d", 30) + background(200, 10)
    profiles = make_csv(tmp_path, "p.csv", [{"username": u, "label": "bot" if u in "abc" else "human"}
                                            for u in sorted({r["username"] for r in rows})])
    result = analyze(make_csv(tmp_path, "c.csv", rows), profiles)
    [swarm] = result["clusters"]
    flags = {a["username"]: a["flagged"] for a in swarm["accounts"]}
    assert flags == {"a": True, "b": True, "c": True, "d": False} and swarm["flagged_members"] == 3
    m = result["metrics"]["at_min_confidence"]
    assert (m["true_positives"], m["false_positives"]) == (3, 0)
    every = analyze(make_csv(tmp_path, "c.csv", rows), profiles, member_ratio=0)
    assert every["metrics"]["at_min_confidence"]["false_positives"] == 1


def test_member_flag_uses_the_unrounded_confidence():
    # confidence 0.37549 shows as 0.375; a share of 0.1876 is under half of the raw value, so not flagged
    import duckdb
    from swarm.core import _clusters
    con = duckdb.connect()
    con.execute("create table cluster (cluster VARCHAR, size BIGINT, confidence DOUBLE)")
    con.execute("create table member (username VARCHAR, cluster VARCHAR, copied_share DOUBLE)")
    con.execute("create table link (u1 VARCHAR, u2 VARCHAR, kind VARCHAR, shared BIGINT, created_together BOOLEAN)")
    con.execute("create table item (username VARCHAR, kind VARCHAR, key UBIGINT, value VARCHAR, first_seen TIMESTAMP, last_seen TIMESTAMP)")
    con.execute("create table profiles (username VARCHAR, display_name VARCHAR, bio VARCHAR, created_at TIMESTAMP)")
    con.execute("insert into cluster values ('c1', 2, 0.37549)")
    con.execute("insert into member values ('a', 'c1', 0.1876), ('b', 'c1', 0.5)")
    [c] = _clusters(con, 0.2, 0.5)
    assert c["confidence"] == 0.375
    assert {a["username"]: a["flagged"] for a in c["accounts"]} == {"a": False, "b": True}
