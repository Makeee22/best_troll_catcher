import json
from swarm.core import analyze
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


def test_without_profiles(tmp_path):
    comments, _ = write(str(tmp_path))
    result = analyze(comments)
    assert result["metrics"] is None and result["source"]["profiles_file"] is None
    assert result["clusters"][0]["created_within_30_days"] is None


def test_min_confidence_cuts_the_list(tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    assert [c["size"] for c in result["clusters"]] == [3]
    assert result["parameters"]["min_confidence"] == 0.5
