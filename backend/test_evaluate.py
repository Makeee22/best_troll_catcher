from swarm.detect import detect
from swarm.evaluate import THRESHOLDS, evaluate
from swarm.load import connect, load
from swarm.synthetic import write


def analysed(tmp_path, with_profiles=True):
    con = connect()
    comments, profiles = write(str(tmp_path))
    load(con, comments, profiles if with_profiles else None)
    detect(con)
    return con


def test_metrics_on_synthetic_data(tmp_path):
    m = evaluate(analysed(tmp_path), 0.2)
    assert m["labelled_accounts"] == 256 and m["labelled_without_content"] == 0
    assert m["at_min_confidence"] == {
        "min_confidence": 0.2, "true_positives": 13, "false_positives": 3, "false_negatives": 0,
        "true_negatives": 240, "precision": 0.8125, "recall": 1.0, "false_positive_rate": 0.0123}
    assert [c["min_confidence"] for c in m["by_threshold"]] == list(THRESHOLDS)
    assert m["by_label"]["benign_feed"] == {"accounts": 3, "flagged": 3}     # the known limit, visible
    assert m["by_label"]["human"] == {"accounts": 240, "flagged": 0}
    assert m["by_label"]["bot:swarm_1"] == {"accounts": 5, "flagged": 5}


def test_a_higher_cut_flags_fewer(tmp_path):
    m = evaluate(analysed(tmp_path), 0.5)        # the swarms sit at 0.375, the feeds at 1.0
    assert m["at_min_confidence"]["true_positives"] == 0
    assert m["at_min_confidence"]["false_positives"] == 3
    assert m["at_min_confidence"]["precision"] == 0.0


def test_no_labels_no_metrics(tmp_path):
    assert evaluate(analysed(tmp_path, with_profiles=False), 0.2) is None


def test_labels_ignore_case_and_spaces(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": u, "text": "some words that make five"} for u in "ab"]),
         make_csv(tmp_path, "p.csv", [{"username": "a", "label": " Bot:X "}, {"username": "b", "label": "HUMAN"}]))
    detect(con)
    m = evaluate(con, 0.2)
    assert m["by_label"] == {"bot:x": {"accounts": 1, "flagged": 0}, "human": {"accounts": 1, "flagged": 0}}
    assert m["at_min_confidence"]["false_negatives"] == 1 and m["at_min_confidence"]["true_negatives"] == 1
