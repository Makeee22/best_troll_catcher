import csv
import json

import pytest

from swarm import convert as convert_module
from swarm.core import analyze
from swarm.convert import ConvertError, convert, is_anonymous, iso_utc, main, merge

COMMENT_COLUMNS = ["comment_id", "username", "text", "timestamp", "parent_id", "thread_id"]
PROFILE_COLUMNS = ["username", "display_name", "created_at", "post_count"]


def row(cid, user, text, ts="", parent="", source="thread", thread=""):
    return {"comment_id": cid, "username": user, "display_name": "", "text": text, "timestamp": ts,
            "parent_id": parent, "thread_id": thread, "source": source}


def test_iso_utc_forms():
    assert iso_utc("2026-06-07T04:24:13.731000+0000") == "2026-06-07T04:24:13Z"
    assert iso_utc("2026-11-14T12:00:00+02:00") == "2026-11-14T10:00:00Z"
    assert iso_utc("2 hours ago") == "" and iso_utc(None) == ""
    assert iso_utc(1763114400) == "2025-11-14T10:00:00Z"


def test_placeholder_authors_are_anonymous():
    for name in ("", "[deleted]", "Anonymous", "Guest", "nimetön", "A Google user",
                 "Verified User in Computer Software", "AutoModerator"):
        assert is_anonymous(name)
    assert not is_anonymous("verified_fan") and not is_anonymous("guestrin")


def test_history_copy_of_a_thread_comment_is_one_comment_and_replies_follow_it():
    # synthetic rows
    thread = row("oq7lyly", "alice", "Hello  world", "2026-11-14T10:00:00Z", source="thread")
    copy = row("19ruo33ofgh8i", "Alice", "hello world", "2026-11-14T10:00:30Z", source="history")
    reply = row("19ruzzz", "bob", "reply", "2026-11-14T10:05:00Z", parent="t1_19ruo33ofgh8i", source="history")
    later = row("19ruyyy", "alice", "Hello world", "2026-11-16T10:00:00Z", source="history")
    comments, _, _ = merge([thread, copy, reply, later], [])
    ids = [c["comment_id"] for c in comments]
    assert ids == ["oq7lyly", "19ruzzz", "19ruyyy"]
    assert comments[1]["parent_id"] == "oq7lyly"


def test_missing_time_matches_only_an_unambiguous_pair():
    one = merge([row("a", "alice", "hi", "2026-11-14T10:00:00Z"), row("b", "alice", "hi", "", source="history")], [])[0]
    assert [c["comment_id"] for c in one] == ["a"]
    two = merge([row("a", "alice", "hi", "2026-11-14T10:00:00Z"), row("c", "alice", "hi", "2026-11-14T11:00:00Z"),
                 row("b", "alice", "hi", "", source="history")], [])[0]
    assert [c["comment_id"] for c in two] == ["a", "c", "b"]


def test_same_id_keeps_the_thread_row_and_prefix_is_stripped():
    comments, _, _ = merge([row("t1_x", "alice", "from history", source="history"), row("x", "alice", "from thread")], [])
    assert [(c["comment_id"], c["text"]) for c in comments] == [("x", "from thread")]


def test_merge_drops_and_counts_anonymous_and_empty():
    comments, _, warnings = merge([row("1", "[deleted]", "x"), row("2", "carol", ""), row("3", "dave", "hi")], [])
    assert [c["username"] for c in comments] == ["dave"]
    assert any("1 comment by an anonymous" in w for w in warnings) and any("1 without text" in w for w in warnings)


def test_profiles_are_deduped_by_username_keeping_first_non_empty():
    profile = lambda u, created="", name="": {"username": u, "display_name": name, "created_at": created, "post_count": ""}
    _, profiles, _ = merge([], [profile("Alice", name="A"), profile("alice", "2020-01-01T00:00:00Z", "B"), profile("bob")])
    assert profiles == [profile("Alice", "2020-01-01T00:00:00Z", "A"), profile("bob")]


def test_bundle_without_any_source_is_an_error():
    with pytest.raises(ConvertError, match="no comments found"):
        convert({"url": "https://example.com", "pages": [{"url": "https://example.com", "role": "thread", "html": "<p>hi</p>"}]})


def test_convert_uses_histories_and_coverage_notes():
    bundle = {"url": "u", "pages": [], "coverage": {"notes": ["the rest are behind a button"]},
              "histories": [{"username": "alice", "status": "failed", "items": [{"id": "z", "text": "skip me"}]},
                            {"username": "bob", "status": "ok", "created_at": "2015-01-01T00:00:00Z",
                             "items": [{"id": "1", "text": "hi", "timestamp": "2026-11-14T10:00:00Z"}]}]}
    comments, profiles, warnings = convert(bundle)
    assert [(c["username"], c["source"]) for c in comments] == [("bob", "history")]
    assert profiles[0]["created_at"] == "2015-01-01T00:00:00Z"
    assert "the rest are behind a button" in warnings


def test_cli_writes_both_files_from_a_bundle_with_histories(tmp_path, capsys):
    # synthetic bundle: one history with two items and created_at
    bundle = {"url": "https://example.com/t", "pages": [],
              "histories": [{"username": "alice", "status": "ok", "created_at": "2015-01-01T00:00:00Z",
                             "items": [{"id": "1", "text": "one", "timestamp": "2026-11-14T10:00:00Z", "parent_id": "", "thread_id": "t"},
                                       {"id": "2", "text": "two", "timestamp": "2026-11-14T11:00:00Z", "parent_id": "1", "thread_id": "t"}]}]}
    src = tmp_path / "bundle.json"
    src.write_text(json.dumps(bundle), encoding="utf-8")
    out = tmp_path / "out"
    assert main([str(src), str(out)]) == 0
    with open(out / "comments.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COMMENT_COLUMNS
        assert len(list(reader)) == 2
    with open(out / "profiles.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == PROFILE_COLUMNS
        assert [r["created_at"] for r in reader] == ["2015-01-01T00:00:00Z"]
    assert "2 comments" in capsys.readouterr().out
    result = analyze(str(out / "comments.csv"), str(out / "profiles.csv"))  # the core must load what we write
    assert result["source"]["comments"] == 2


def test_cli_errors_exit_2(tmp_path, capsys):
    page = tmp_path / "page.html"
    page.write_text("<p>hi</p>", encoding="utf-8")
    assert main([str(page), str(tmp_path / "out")]) == 2
    assert "error: no comments found" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.json"), str(tmp_path / "out")]) == 2


def test_comment_display_name_reaches_profiles():
    named = dict(row("1", "u123", "hi"), display_name="Helpful Bot")
    _, profiles, _ = merge([named], [])
    assert profiles == [{"username": "u123", "display_name": "Helpful Bot", "created_at": "", "post_count": ""}]


def test_fall_through_to_html_keeps_parsed_profiles_and_notes(monkeypatch):
    profile = {"username": "p", "display_name": "", "created_at": "2020-01-01T00:00:00Z", "post_count": ""}
    monkeypatch.setattr(convert_module.sites, "from_parsed", lambda parsed, url: ([], [profile], ["parsed note"]))
    monkeypatch.setattr(convert_module.sites, "from_html", lambda html, url: ([row("1", "dave", "hi")], [], ["html note"]))
    comments, profiles, warnings = convert({"url": "u", "pages": [{"parsed": {"type": "x"}, "html": "<p>x</p>"}]})
    assert [c["username"] for c in comments] == ["dave"]
    assert [p["username"] for p in profiles] == ["p"]
    assert "parsed note" in warnings and "html note" in warnings


def test_integer_ids_and_names_do_not_crash():
    bundle = {"url": "u", "pages": [], "histories": [{"username": 42, "status": "ok", "items": [
        {"id": 1, "text": "one", "parent_id": 0}, {"id": 2, "text": "two", "parent_id": 1}]}]}
    comments, _, _ = convert(bundle)
    assert [(c["comment_id"], c["username"], c["parent_id"]) for c in comments] == [("1", "42", ""), ("2", "42", "1")]


def test_history_without_id_never_registers_an_alias():
    thread = row("c1", "alice", "hello", "2026-11-14T10:00:00Z", parent="")
    root = row("c2", "bob", "other", "2026-11-14T10:01:00Z", parent="")
    copy = row("", "alice", "hello", "2026-11-14T10:00:10Z", source="history")
    comments, _, _ = merge([thread, root, copy], [])
    assert [c["parent_id"] for c in comments] == ["", ""]
