import importlib.util
import random
import subprocess
import sys

import pytest

from swarm.detect import detect
from swarm.load import InputError, connect, load
from swarm import similar
from swarm.similar import add_items
from swarm.synthetic import write

HAS_MODEL2VEC = importlib.util.find_spec("model2vec") is not None
needs_model2vec = pytest.mark.skipif(not HAS_MODEL2VEC, reason="model2vec not installed")


@pytest.fixture(autouse=True)
def small_model(monkeypatch):
    """The 30 MB English model: the default multilingual one is a 512 MB download."""
    monkeypatch.setattr(similar, "MODEL", similar.ENGLISH_MODEL)


def multilingual_cached():
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(similar.MULTILINGUAL_MODEL, "model.safetensors"), str)


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


@needs_model2vec
def test_reworded_swarm_is_found_with_the_layer(tmp_path):
    con, signals, _ = run(tmp_path, similar_text=True)
    found = clusters(con)
    assert {f"troll_2_{i}" for i in range(6)} in found
    assert not any(n.startswith(("user_", "fan_")) for g in found for n in g)
    assert signals["similar_text"]["status"] == "used" and signals["similar_text"]["items"] > 0


@needs_model2vec
def test_a_reworded_swarm_is_found_in_clean_background(tmp_path, make_csv):
    # the background's only near-duplicates are chance pairs of word bags, so the rate must come from all texts:
    # counted among grouped texts alone it is 0.022 here and the swarm is missed
    variants = [("the council voted to close the old library on main street next spring",
                 "the council has voted to close the old library on main street next spring"),
                ("our mayor is lying to you about the new bridge and its real cost",
                 "our mayor keeps lying to you about the new bridge and its real cost"),
                ("share this before they delete it from every page on the internet today",
                 "share this now before they delete it from every page on the internet")]
    rows = [{"username": u, "text": v[k % 2]} for v in variants for k, u in enumerate("abc")]
    words = ("river garden coffee winter summer train ticket music movie dinner cousin weekend market bakery "
             "school teacher forest beach cloud rain snow bicycle kitchen window letter").split()
    rng = random.Random(0)
    rows += [{"username": u, "text": " ".join(rng.sample(words, 8))} for u in [*"abc"] + [f"bg{k}" for k in range(40)]
             for _ in range(10)]
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows))
    detect(con, similar_text=True)
    assert clusters(con) == [{"a", "b", "c"}]


def _similar_item_count(tmp_path, make_csv, rows, threshold=0.5):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments")
    reason, _ = add_items(con, threshold=threshold)
    assert reason is None
    return con.execute("select count(*) from item where kind = 'similar_text'").fetchall()[0][0]


@needs_model2vec
def test_groups_of_word_for_word_copies_still_add_items(tmp_path, make_csv):
    first, second = "the council voted on a new budget for schools today", "the council voted on a new budget for roads today"
    rows = [{"username": u, "text": t} for u in "abc" for t in (first, second)]
    assert _similar_item_count(tmp_path, make_csv, rows) == 3          # recall over counting once


@needs_model2vec
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


@needs_model2vec
def test_too_many_near_duplicate_pairs_skips(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments where text like '%council%'")
    reason, _ = add_items(con, max_pairs=1, threshold=0.0)
    assert reason and "near-duplicate" in reason


@needs_model2vec
def test_oversized_groups_are_left_out_with_a_warning(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    detect(con)
    con.execute("create or replace table text_norm as select distinct hash(text) as key, text as norm from comments where text like '%council%'")
    reason, warnings = add_items(con, threshold=0.0, max_group=3)
    assert reason is None and any("left out" in w for w in warnings)


@needs_model2vec
def test_model_failure_is_an_input_error_not_a_traceback(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("no network")
    import model2vec
    monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", fail)
    from swarm import similar
    similar._model.cache_clear()   # a model loaded by an earlier test would hide the failure
    con = connect()
    load(con, *write(str(tmp_path), reworded=True))
    with pytest.raises(InputError, match="no network"):
        detect(con, similar_text=True)


def test_core_imports_without_numpy():
    code = "import sys; import swarm.detect, swarm.core, swarm.api; sys.exit('numpy' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


@pytest.mark.skipif(not (HAS_MODEL2VEC and multilingual_cached()), reason="multilingual model not downloaded")
def test_finnish_rewordings_become_one_item_and_unrelated_texts_do_not(tmp_path, make_csv, monkeypatch):
    monkeypatch.setattr(similar, "MODEL", similar.MULTILINGUAL_MODEL)
    pairs = [("hallitus nostaa taas veroja ensi vuonna eikä kukaan kysy kansalaisten mielipidettä",
              "hallitus nostaa jälleen veroja ensi vuonna eikä kukaan kysy kansalaisten mielipidettä"),
             ("kaupunki käyttää rahaa uuteen siltaan ja se on pelkkää haaskausta sanon minä",
              "kaupunki käyttää rahaa uuteen siltaan ja se on pelkkää tuhlausta sanon minä")]
    rows = [{"username": u, "text": pair[k % 2]} for pair in pairs for k, u in enumerate("abc")]
    rows += [{"username": "d", "text": t} for t in ("kävin eilen mökillä ja järvi oli jo melkein jäässä",
                                                     "hallitus esitteli eilen uuden budjetin eduskunnalle")]
    assert _similar_item_count(tmp_path, make_csv, rows, threshold=similar.THRESHOLD) == 6    # a, b, c twice; d none
