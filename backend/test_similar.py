import pytest

pytest.importorskip("model2vec")

from swarm.detect import detect  # noqa: E402
from swarm.load import connect, load  # noqa: E402
from swarm.similar import add_items  # noqa: E402
from swarm.synthetic import write  # noqa: E402


def clusters(con):
    out = {}
    for cluster, username in con.execute("select cluster, username from member").fetchall():
        out.setdefault(cluster, set()).add(username)
    return list(out.values())


def run(tmp_path, **kwargs):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    detect(con, **kwargs)
    return con


def test_reworded_swarm_is_missed_without_the_layer(tmp_path):
    assert not any(n.startswith("troll_2_") for g in clusters(run(tmp_path)) for n in g)


def test_reworded_swarm_is_found_with_the_layer(tmp_path):
    found = clusters(run(tmp_path, similar_text=True))
    assert {f"troll_2_{i}" for i in range(6)} in found
    assert not any(n.startswith(("user_", "fan_")) for g in found for n in g)


def test_too_many_texts_skips_with_a_warning(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    con.execute("create or replace table text_norm as select hash(text) as key, text as norm from comments where text is not null")
    before = con.execute("select count(*) from item").fetchall()[0][0]
    warnings = add_items(con, max_texts=10)
    assert warnings and con.execute("select count(*) from item").fetchall()[0][0] == before
