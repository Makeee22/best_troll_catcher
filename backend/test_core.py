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
    assert result["parameters"] == {"min_words": 5, "min_shared": 2, "alpha": 0.01, "min_size": 3, "min_confidence": 0.2}
    assert [c["size"] for c in result["clusters"]] == [3, 8, 5]            # feeds at 1.0, then the swarms
    assert result["metrics"]["at_min_confidence"]["precision"] == 0.8125
    swarm = result["clusters"][1]
    assert set(swarm) == {"id", "size", "confidence", "accounts", "edge_count", "edges", "top_items",
                          "first_seen", "last_seen", "created_within_30_days"}
    assert swarm["confidence"] == 0.375 and swarm["edge_count"] == 28 and len(swarm["edges"]) == 28
    assert swarm["accounts"][0] == {"username": "troll_0_0", "copied_share": 0.375}
    assert swarm["edges"][0].keys() == {"source", "target", "kind", "shared"}
    assert len(swarm["top_items"]) == 6 and swarm["top_items"][0]["accounts"] == 8
    assert swarm["top_items"][0]["kind"] == "text" and swarm["top_items"][0]["first_seen"].endswith("Z")
    assert swarm["created_within_30_days"] == {"accounts": 8, "of": 8}


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
