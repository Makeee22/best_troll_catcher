import subprocess
import sys

import pytest

from swarm.detect import detect
from swarm.load import InputError, connect, load
from swarm.similar import add_items
from swarm.synthetic import write

model2vec = pytest.importorskip("model2vec")


def clusters(con):
    out = {}
    for cluster, username in con.execute("select cluster, username from member").fetchall():
        out.setdefault(cluster, set()).add(username)
    return list(out.values())


def run(tmp_path, **kwargs):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    signals, warnings = detect(con, **kwargs)
    return con, signals, warnings


def test_reworded_swarm_is_missed_without_the_layer(tmp_path):
    con, signals, _ = run(tmp_path)
    assert "similar_text" not in signals
    assert not any(n.startswith("troll_2_") for g in clusters(con) for n in g)


def test_reworded_swarm_is_found_with_the_layer(tmp_path):
    con, signals, _ = run(tmp_path, similar_text=True)
    found = clusters(con)
    assert {f"troll_2_{i}" for i in range(6)} in found
    assert not any(n.startswith(("user_", "fan_")) for g in found for n in g)
    assert signals["similar_text"]["status"] == "used" and signals["similar_text"]["items"] > 0


def _similar_item_count(tmp_path, make_csv, rows):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments")
    reason, _ = add_items(con, threshold=0.5)
    assert reason is None
    return con.execute("select count(*) from item where kind = 'similar_text'").fetchall()[0][0]


def test_groups_of_word_for_word_copies_add_no_similar_items(tmp_path, make_csv):
    first, second = "the council voted on a new budget for schools today", "the council voted on a new budget for roads today"
    rows = [{"username": u, "text": t} for u in "abc" for t in (first, second)]
    assert _similar_item_count(tmp_path, make_csv, rows) == 0


def test_a_group_with_a_one_off_variant_adds_items(tmp_path, make_csv):
    first, second = "the council voted on a new budget for schools today", "the council voted on a new budget for roads today"
    rows = [{"username": u, "text": t} for u in "abc" for t in (first, second)]
    rows.append({"username": "d", "text": "the council voted on a new budget for homes today"})
    assert _similar_item_count(tmp_path, make_csv, rows) == 4        # a, b, c, d each get the group's item


def test_skipped_with_a_reason_when_it_cannot_run(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": f"u{i}", "repost_of": "p1"} for i in range(5)]))
    signals, warnings = detect(con, similar_text=True)
    assert signals["similar_text"]["status"] == "skipped" and "text" in signals["similar_text"]["reason"]
    con = connect()
    load(con, make_csv(tmp_path, "d.csv", [{"username": "a", "text": "just one text of five words"}]))
    signals, warnings = detect(con, similar_text=True)
    assert signals["similar_text"]["status"] == "skipped" and "fewer than 2" in signals["similar_text"]["reason"]
    assert any("similar_text skipped" in w for w in warnings)


def test_too_many_texts_skips_with_a_reason(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    con.execute("create or replace table text_norm as select hash(text) as key, text as norm from comments where text is not null")
    before = con.execute("select count(*) from item").fetchall()[0][0]
    reason, _ = add_items(con, max_texts=10)
    assert reason and con.execute("select count(*) from item").fetchall()[0][0] == before


def test_too_many_near_duplicate_pairs_skips(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments where text like '%council%'")
    reason, _ = add_items(con, max_pairs=1, threshold=0.0)
    assert reason and "near-duplicate" in reason


def test_oversized_groups_are_left_out_with_a_warning(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments where text like '%council%'")
    reason, warnings = add_items(con, threshold=0.0, max_group=3)
    assert reason is None and any("left out" in w for w in warnings)


def test_model_failure_is_an_input_error_not_a_traceback(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("no network")
    monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", fail)
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    with pytest.raises(InputError, match="no network"):
        detect(con, similar_text=True)


def test_core_imports_without_numpy():
    code = "import sys; import swarm.detect, swarm.core, swarm.api; sys.exit('numpy' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
