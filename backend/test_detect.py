import pytest
from swarm.detect import detect
from swarm.load import InputError, connect, load
from swarm.synthetic import generate, write

WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima".split()


def unique(owner, n):
    """n texts nobody else has."""
    return [{"username": owner, "text": f"{owner} wrote note number {i} about {WORDS[i % 12]} today"} for i in range(n)]


def shared(owners, n, tag="plan"):
    return [{"username": o, "text": f"the {tag} for item {i} is ready for everyone now"} for i in range(n) for o in owners]


def background(n_accounts, n_texts):
    return [row for a in range(n_accounts) for row in unique(f"bg{a}", n_texts)]


def run(tmp_path, make_csv, rows, **kwargs):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows))
    signals, warnings = detect(con, **kwargs)
    return con, signals, warnings


def clusters(con):
    members = con.execute("select cluster, username from member order by 1, 2").fetchall()
    out = {}
    for cluster, username in members:
        out.setdefault(cluster, set()).add(username)
    return list(out.values())


def test_synthetic_swarms_are_found_and_ordinary_users_are_in_no_cluster(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    found = clusters(con)
    assert {f"troll_0_{i}" for i in range(8)} in found
    assert {f"troll_1_{i}" for i in range(5)} in found
    # breaking news, a viral repost, a greeting and a fan community link nobody
    assert not any(name.startswith(("user_", "fan_")) for group in found for name in group)
    confidence = dict(con.execute("select size, round(confidence, 3) from cluster").fetchall())
    assert confidence[8] == 0.375 and confidence[5] == 0.375      # 6 of 16 items are shared


def test_benign_feeds_are_flagged_known_limit(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    assert {"newsfeed_0", "newsfeed_1", "newsfeed_2"} in clusters(con)


def test_one_shared_item_links_nobody(tmp_path, make_csv):
    rows = shared(["a", "b", "c"], 1) + unique("a", 5) + unique("b", 5) + unique("c", 5) + background(50, 20)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == []


def test_everyone_sharing_everything_is_not_surprising(tmp_path, make_csv):
    rows = [{"username": f"u{a}", "text": f"see https://x.example/{k}"} for a in range(10) for k in range(3)]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == []


def test_loose_group_is_a_cluster_with_low_confidence(tmp_path, make_csv):
    trio = ["a", "b", "c"]
    rows = shared(trio, 6) + [r for o in trio for r in unique(o, 40)] + background(50, 40)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [set(trio)]
    assert con.execute("select round(confidence, 3) from cluster").fetchall() == [(0.13,)]   # 6 of 46


def test_copies_differ_by_case_mentions_and_links_in_any_script(tmp_path, make_csv):
    variants = ["Привет всем это важная новость номер {i}", "@bob ПРИВЕТ всем это важная новость номер {i} https://x.example/a",
                "привет ВСЕМ, это важная новость номер {i}!"]
    rows = [{"username": o, "text": v.format(i=i)} for i in range(6) for o, v in zip("abc", variants)]
    rows += [r for o in "abc" for r in unique(o, 10)] + background(50, 20)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [{"a", "b", "c"}]


def test_a_repost_gives_only_its_repost_item(tmp_path, make_csv):
    rows = [{"username": "a", "text": "RT this is the original text of the post https://x.example/1", "repost_of": "p1", "parent_id": "q1"}]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select kind, value from item").fetchall() == [("repost", "p1")]


def test_an_account_repeating_itself_is_one_item_and_no_link(tmp_path, make_csv):
    rows = [{"username": o, "text": f"{o} says the very same thing again and again"} for o in "abc" for _ in range(50)]
    con, signals, _ = run(tmp_path, make_csv, rows + background(20, 5))
    assert con.execute("select count(*) from item where username in ('a', 'b', 'c')").fetchall() == [(3,)]
    assert clusters(con) == []


def test_text_without_words_gives_no_item(tmp_path, make_csv):
    rows = [{"username": "a", "text": t} for t in ["😀😀😀😀😀😀", "!!! ... ???", "   ", "too short"]] + unique("b", 3)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select count(*) from item where username = 'a'").fetchall() == [(0,)]


def test_missing_columns_skip_their_signals(tmp_path, make_csv):
    comments, _ = generate()
    rows = [{"username": c["username"], "text": c["text"]} for c in comments]
    con, signals, _ = run(tmp_path, make_csv, rows)
    assert signals["text"]["status"] == "used" and signals["text"]["links"] > 0
    assert signals["repost"] == {"status": "skipped", "reason": signals["repost"]["reason"], "items": 0, "links": 0}
    assert "repost_of" in signals["repost"]["reason"]
    assert {f"troll_0_{i}" for i in range(8)} in clusters(con)


def test_no_content_column_at_all_is_an_input_error(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": "a", "timestamp": "2026-11-01T10:00:00Z"}]))
    with pytest.raises(InputError, match="text.*links.*repost_of.*parent_id"):
        detect(con)


def test_a_tiny_pair_budget_warns_instead_of_failing(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    signals, warnings = detect(con, pair_budget=10)
    assert any("budget" in w.lower() for w in warnings)
