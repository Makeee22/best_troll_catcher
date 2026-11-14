import json
import os
import tempfile
from collections import Counter
from dataclasses import replace

from swarm import inject
from swarm.core import analyze
from swarm.synthetic import write

BASE = inject.Scenario()


def _background(tmp_path):
    return write(str(tmp_path / "bg"), seed=0)[0]


def _differences(a, b):
    a, b = a.split(), b.split()
    return len(a) != len(b) or sum(x != y for x, y in zip(a, b))


def test_plant_is_deterministic_and_seeded():
    assert inject.plant(BASE, 1) == inject.plant(BASE, 1)
    assert inject.plant(BASE, 1) != inject.plant(BASE, 2)


def test_plant_counts_and_names():
    for s in (BASE, replace(BASE, size=20, participation=0.25, own=3), replace(BASE, size=3, participation=0.25, own=0)):
        rows = inject.plant(s, 0)
        assert len(rows) == s.size * s.own + s.messages * max(2, round(s.size * s.participation))
        assert all(r["username"].startswith("planted_") and r["timestamp"].endswith("Z") for r in rows)


def test_plant_exact_copies_and_unique_own_posts():
    s = replace(BASE, participation=0.5)
    counts = Counter(r["text"] for r in inject.plant(s, 0))
    copies = [n for n in counts.values() if n > 1]
    assert len(copies) == s.messages and set(copies) == {4}
    assert Counter(counts.values()) == {4: s.messages, 1: s.size * s.own}


def test_plant_edited_copies_differ_by_one_word():
    rows = inject.plant(replace(BASE, variant="edited", messages=1, own=0), 0)
    assert len(rows) == 8 and len({r["text"] for r in rows}) > 1
    assert all(_differences(a["text"], b["text"]) <= 2 for a in rows for b in rows)


def test_plant_reworded_uses_the_synonym_vocabulary():
    rows = inject.plant(replace(BASE, variant="reworded", messages=1, own=0), 0)
    assert len(rows) == 8 and all(len(r["text"].split()) == 15 for r in rows)


def test_run_base_scenario(tmp_path):
    path = _background(tmp_path)
    result = inject.run(path, [BASE])
    direct = analyze(path)
    flagged = {a["username"] for c in direct["clusters"] for a in c["accounts"]}
    assert result["background"]["flagged"] == len(flagged)
    assert result["background"]["accounts"] == direct["source"]["accounts"]
    row = result["scenarios"][0]
    assert row["planted_flagged"] == 8 and isinstance(row["confidence"], float)
    assert isinstance(row["background_flagged"], int) and row["background_flagged"] >= 0
    json.dumps(result)


def test_run_leaves_the_background_and_temp_files_alone(tmp_path, monkeypatch):
    path = _background(tmp_path)
    before = open(path, "rb").read()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    inject.run(path, [BASE])
    assert open(path, "rb").read() == before
    assert os.listdir(scratch) == []


def test_missing_text_column_is_an_input_error(tmp_path, make_csv, capsys):
    path = make_csv(tmp_path, "c.csv", [{"username": "a", "body": "hello there"}])
    assert inject.main([path]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_grid_has_no_duplicates_and_one_base_case():
    assert len(set(inject.GRID)) == len(inject.GRID)
    assert inject.GRID.count(BASE) == 1


def test_main_writes_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(inject, "GRID", [BASE, replace(BASE, size=3, messages=1)])
    out = tmp_path / "out.json"
    assert inject.main([_background(tmp_path), "--out", str(out)]) == 0
    assert len(json.loads(out.read_text())["scenarios"]) == 2
    assert capsys.readouterr().out.rstrip().endswith("assumed not to be coordinated.")
