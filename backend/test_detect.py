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


def one_text(owners, n_words):
    """One text of exactly n_words words (at most 13), posted once by each owner."""
    return [{"username": o, "text": " ".join(WORDS[:n_words - 1] + ["end"])} for o in owners]


def trio(n_words):
    """a, b, c share one text of n_words words and have a few of their own; many other accounts keep chance matches rare."""
    return one_text("abc", n_words) + unique("a", 5) + unique("b", 5) + unique("c", 5) + background(300, 20)


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


def test_one_shared_short_text_links_nobody(tmp_path, make_csv):   # 7 words: under LONG_WORDS
    con, _, _ = run(tmp_path, make_csv, trio(7))
    assert clusters(con) == []


def test_one_shared_long_text_links_a_cluster(tmp_path, make_csv):
    con, _, _ = run(tmp_path, make_csv, trio(12))
    assert clusters(con) == [{"a", "b", "c"}]
    assert con.execute("select max(words) from item where username = 'a' and kind = 'text'").fetchall() == [(12,)]
    assert con.execute("select count(*) from item where kind <> 'text' and words is not null").fetchall() == [(0,)]


def test_a_shared_long_text_is_not_hidden_by_many_own_posts(tmp_path, make_csv):
    # the chance of a match counts pairs of different posts, so a post never "matches" itself
    rows = one_text("abc", 12) + unique("a", 60) + unique("b", 60) + unique("c", 60) + background(300, 20)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [{"a", "b", "c"}]


def test_the_long_text_rule_can_be_switched_off(tmp_path, make_csv):
    for off in (None, 0):
        con, _, _ = run(tmp_path, make_csv, trio(12), long_words=off)
        assert clusters(con) == []


def test_a_long_text_posted_by_many_links_nobody(tmp_path, make_csv):
    # 40 of 60 accounts post it once: a pair is expected to share it by chance about 0.8 times.
    # x, y, z share 20 texts, which keeps the chance test's cut in reach, so only that test rejects the 40.
    rows = one_text([f"bg{a}" for a in range(40)], 12) + background(60, 20) + shared("xyz", 20, tag="swarm")
    rows += [r for o in "xyz" for r in unique(o, 5)]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [{"x", "y", "z"}]


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


def test_links_are_compared_after_normalising(tmp_path, make_csv):
    posted = {"a": "HTTP://WWW.Example.com/a/?utm_source=x#top", "b": "https://example.com/a",
              "c": "http://example.com/a/?fbclid=1", "d": "https://example.com/A",
              "e": "https://example.com/a?id=5&utm_medium=y", "f": "https://example.com/a?id=5"}
    con, _, _ = run(tmp_path, make_csv, [{"username": u, "text": f"read {url}"} for u, url in posted.items()])
    key = dict(con.execute("select username, key from item where kind = 'link'").fetchall())
    assert key["a"] == key["b"] == key["c"]
    assert key["d"] != key["a"] and key["e"] == key["f"] != key["a"]
    assert con.execute("select value from item where username = 'a' and kind = 'link'").fetchall() == [(posted["a"],)]


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


def _with_profiles(tmp_path, make_csv, rows, created):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows), make_csv(tmp_path, "p.csv", [{"username": u, "created_at": t} for u, t in created.items()]))
    signals, _ = detect(con)
    return con, signals


def _old_dates(accounts):
    """Creation dates spread over ten years, about 30 days apart: nobody else is born together."""
    from datetime import date, timedelta
    return {u: (date(2012, 1, 1) + timedelta(days=37 * k)).isoformat() + "T00:00:00Z" for k, u in enumerate(accounts)}


def test_one_shared_short_text_links_accounts_created_together(tmp_path, make_csv):
    # Test R: a swarm pastes short stock phrases and its accounts were made in one batch; one phrase alone links nobody
    rows = trio(7)
    created = _old_dates(sorted({r["username"] for r in rows} - set("abc")))
    created.update({"a": "2026-10-01T00:00:00Z", "b": "2026-10-05T00:00:00Z", "c": "2026-10-20T00:00:00Z"})
    con, signals = _with_profiles(tmp_path, make_csv, rows, created)
    assert clusters(con) == [{"a", "b", "c"}]
    assert signals["created_together"]["status"] == "used" and signals["created_together"]["links"] == 3
    assert con.execute("select bool_and(created_together) from link").fetchall()[0][0] is True


def test_created_together_alone_links_nobody_and_old_spread_accounts_stay_unlinked(tmp_path, make_csv):
    rows = trio(7)
    accounts = sorted({r["username"] for r in rows})
    con, _ = _with_profiles(tmp_path, make_csv, rows, _old_dates(accounts))   # a, b, c share the phrase but not a birth month
    assert clusters(con) == []
    batch = unique("x", 5) + unique("y", 5) + unique("z", 5) + background(300, 20)   # born together, share nothing
    created = _old_dates(sorted({r["username"] for r in batch} - set("xyz")))
    created.update({"x": "2026-10-01T00:00:00Z", "y": "2026-10-02T00:00:00Z", "z": "2026-10-03T00:00:00Z"})
    (tmp_path / "b").mkdir()
    con, _ = _with_profiles(tmp_path / "b", make_csv, batch, created)
    assert clusters(con) == []


def test_a_month_when_everyone_was_created_proves_little(tmp_path, make_csv):
    # every account born in the same month: being born together is no surprise, so one phrase still links nobody
    rows = trio(7)
    created = {u: "2026-10-01T00:00:00Z" for u in {r["username"] for r in rows}}
    con, signals = _with_profiles(tmp_path, make_csv, rows, created)
    assert clusters(con) == [] and signals["created_together"]["items"] == 303


def test_created_together_can_be_switched_off(tmp_path, make_csv):
    rows = trio(7)
    created = _old_dates(sorted({r["username"] for r in rows} - set("abc")))
    created.update({"a": "2026-10-01T00:00:00Z", "b": "2026-10-05T00:00:00Z", "c": "2026-10-20T00:00:00Z"})
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows), make_csv(tmp_path, "p.csv", [{"username": u, "created_at": t} for u, t in created.items()]))
    signals, _ = detect(con, created_days=0)
    assert clusters(con) == [] and signals["created_together"]["status"] == "skipped"


def test_confidence_counts_only_the_kinds_that_link_the_cluster(tmp_path, make_csv):
    # Fox8-23's shape: members repost each other and write their own text that nobody copies; the text must not dilute
    rows = [{"username": u, "repost_of": f"post{i}"} for u in "abc" for i in range(6)]
    rows += unique("a", 30) + unique("b", 30) + unique("c", 30)
    rows += [{"username": f"bg{k}", "repost_of": f"other{k}_{i}"} for k in range(40) for i in range(6)] + background(40, 10)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select size, confidence from cluster").fetchall() == [(3, 1.0)]   # 6 of 36 posts over all kinds
    assert con.execute("select count(*) from member where copied_share = 1.0").fetchall()[0][0] == 3


def test_a_few_text_links_do_not_bring_back_the_uncopied_text(tmp_path, make_csv):
    # Fox8-23 as J0l3s measured it: a repost ring where a few member pairs also share text; weighting by links keeps the
    # reposts in charge (all kinds counted equally: about 0.2, so it fell under a cut of 0.3)
    rows = [{"username": u, "repost_of": f"post{i}"} for u in "abcdef" for i in range(6)]
    rows += [row for u in "abcdef" for row in unique(u, 30)] + shared("ab", 2)
    rows += [{"username": f"bg{k}", "repost_of": f"other{k}_{i}"} for k in range(40) for i in range(6)] + background(40, 10)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select kind, count(*) from link group by kind order by kind").fetchall() == [("repost", 15), ("text", 1)]
    [(size, confidence)] = con.execute("select size, confidence from cluster").fetchall()
    assert size == 6 and confidence > 0.9


def _thread(readers, parents, thread="t1"):
    """Each reader replies once to each parent post of one thread, in words of its own (handoff 6e, R7)."""
    return [{"username": r, "comment_id": f"{r}-{p}", "parent_id": p, "thread_id": thread,
             "text": f"{r} answers {p} with thoughts on {WORDS[i % 12]} only"} for r in readers for i, p in enumerate(parents)]


def _history(owner, n):
    """n posts of the owner's own, each in a thread of its own, replying to posts nobody else answers."""
    return [{"username": owner, "comment_id": f"{owner}-h{i}", "parent_id": f"{owner}-p{i}", "thread_id": f"{owner}-t{i}",
             "text": f"{owner} wrote note number {i} about {WORDS[i % 12]} today"} for i in range(n)]


def test_readers_seen_only_in_the_thread_are_not_linked_for_replying_to_its_top_posts(tmp_path, make_csv):
    readers = [f"r{i}" for i in range(10)]
    others = [f"h{i}" for i in range(40)]
    rows = _thread(readers + others, ["root", "top"]) + [r for h in others for r in _history(h, 25)]
    con, signals, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == []
    assert con.execute("select count(*) from thread_only").fetchall() == [(10,)]
    assert con.execute("select count(*) from item where kind = 'reply' and username like 'r%'").fetchall() == [(0,)]


def test_accounts_seen_only_in_one_thread_still_link_on_copied_text(tmp_path, make_csv):
    swarm = [f"s{i}" for i in range(6)]
    rows = [{"username": s, "comment_id": f"{s}-{i}", "thread_id": "page", "parent_id": "page",
             "text": f"best product ever bought number {i} five stars"} for s in swarm for i in range(3)]
    rows += [{"username": f"u{a}", "comment_id": f"u{a}-{i}", "thread_id": "page", "parent_id": "page",
              "text": f"u{a} reviews it as {WORDS[i % 12]} and {WORDS[(a + i) % 12]} fine"} for a in range(60) for i in range(3)]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [set(swarm)]
