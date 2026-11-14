from swarm.collect import _explain_collection
from swarm.core import analyze
from swarm.synthetic import write
from test_detect import WORDS, _history, _thread


def codes(result):
    return [r["code"] for r in result["diagnostics"]["reasons"]]


def test_nothing_shared_says_so(tmp_path, make_csv):
    rows = [{"username": f"u{a}", "text": f"u{a} wrote note {i} about {WORDS[i % 12]} and more"} for a in range(5) for i in range(4)]
    result = analyze(make_csv(tmp_path, "c.csv", rows))
    assert result["clusters"] == []
    assert codes(result) == ["nothing_shared_enough"]
    assert result["diagnostics"]["accounts"] == 5 and result["diagnostics"]["main_thread"] is None


def test_readers_of_one_thread_are_explained(tmp_path, make_csv):
    readers, others = [f"r{i}" for i in range(10)], [f"h{i}" for i in range(40)]
    rows = _thread(readers + others, ["root", "top"], thread="root") + [r for h in others for r in _history(h, 25)]
    result = analyze(make_csv(tmp_path, "c.csv", rows))
    d = result["diagnostics"]
    assert result["clusters"] == [] and d["thread_only_accounts"] == 10
    assert [w["accounts"] for w in d["widest_items"][:2]] == [50, 50]
    assert sorted(w["opening_post"] for w in d["widest_items"][:2]) == [False, True]   # the root and the top comment
    assert "explained_by_chance" in codes(result) and "thin_histories" not in codes(result)   # 10 of 50 is under 0.3
    assert d["by_kind"]["reply"]["pairs_sharing_enough"] > 0 and d["by_kind"]["reply"]["pairs_linked"] == 0
    assert d["main_thread"]["accounts"] == 50


def test_a_found_swarm_gives_no_nothing_found_reason(tmp_path):
    result = analyze(*write(str(tmp_path)))
    d = result["diagnostics"]
    assert d["groups_found"] >= len(result["clusters"]) > 0
    assert not {"nothing_shared_enough", "no_group", "below_cut"} & set(codes(result))
    assert sum(k["pairs_linked"] for k in d["by_kind"].values()) > 0


def test_collection_coverage_is_explained():
    result = {"diagnostics": {"reasons": [{"code": "no_group", "text": "x"}]}}
    bundle = {"credits_used": 3, "coverage": {"comments_found": 289, "comments_expected": 817},
              "thread": {"platform": "Bluesky", "commenters": 400, "commenters_fetched": 150, "histories_ok": 148}}
    _explain_collection(result, bundle)
    assert result["collection"]["comments_expected"] == 817 and result["collection"]["histories_ok"] == 148
    assert codes(result) == ["capped_histories", "partial_thread", "no_group"]
