import json
from fastapi.testclient import TestClient
from swarm.core import analyze
from swarm.synthetic import write


def client(monkeypatch, **env):
    for name in ("RESULT_FILE", "COMMENTS_FILE", "PROFILES_FILE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import importlib
    import swarm.api
    return TestClient(importlib.reload(swarm.api).app)


def test_default_is_the_synthetic_sample(monkeypatch):
    c = client(monkeypatch)
    assert c.get("/health").json() == {"status": "ok"}
    body = c.get("/api/swarms").json()
    assert body["source"]["synthetic"] is True and len(body["swarms"]) == 3
    first = body["swarms"][0]
    assert set(first) == {"id", "size", "confidence", "edge_count", "first_seen", "last_seen", "sample", "declared_automation"}
    detail = c.get(f"/api/swarms/{first['id']}").json()
    assert detail["id"] == first["id"] and detail["accounts"]
    assert c.get("/api/swarms/nope").status_code == 404
    assert c.get("/api/metrics").json()["metrics"]["at_min_confidence"]["precision"] == 0.8125


def test_serves_a_result_file(monkeypatch, tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert len(client(monkeypatch, RESULT_FILE=str(path)).get("/api/swarms").json()["swarms"]) == 1


def test_serves_a_result_file_written_before_declared_automation(monkeypatch, tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    for c in result["clusters"]:
        del c["declared_automation"]
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert client(monkeypatch, RESULT_FILE=str(path)).get("/api/swarms").json()["swarms"][0]["declared_automation"] is None


def test_analyses_a_comments_file(monkeypatch, tmp_path):
    comments, _ = write(str(tmp_path))
    body = client(monkeypatch, COMMENTS_FILE=comments).get("/api/metrics").json()
    assert body["metrics"] is None and body["source"]["profiles_file"] is None


def test_unreadable_input_stops_startup_with_a_message(monkeypatch, tmp_path):
    import pytest
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    for env in ({"RESULT_FILE": str(bad)}, {"RESULT_FILE": str(tmp_path / "nope.json")},
                {"COMMENTS_FILE": str(tmp_path / "nope.csv")}):
        with pytest.raises(SystemExit, match="RESULT_FILE|COMMENTS_FILE"):
            client(monkeypatch, **env)
