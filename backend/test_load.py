import pytest
from swarm.load import COMMENT_COLUMNS, PROFILE_COLUMNS, InputError, connect, load


def rows(con, sql):
    return con.execute(sql).fetchall()


def test_minimal_file_gets_every_standard_column(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "text": "hello"}, {"username": "bob", "text": ""}]))
    assert [r[0] for r in rows(con, "describe comments")] == COMMENT_COLUMNS
    assert [r[0] for r in rows(con, "describe profiles")] == PROFILE_COLUMNS
    assert rows(con, "select comment_id, username, text, timestamp from comments order by 1") == [("1", "ann", "hello", None), ("2", "bob", None, None)]
    assert rows(con, "select count(*) from profiles") == [(0,)]
    assert any("timestamp" in w for w in warnings)


def test_header_case_spaces_and_unknown_columns(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(" Username ,TEXT,shoe_size\nann,hi,42\n", encoding="utf-8")
    con = connect()
    warnings = load(con, str(path))
    assert rows(con, "select username, text from comments") == [("ann", "hi")]
    assert any("shoe_size" in w for w in warnings)


def test_semicolons_and_byte_order_mark(tmp_path):
    path = tmp_path / "c.csv"
    path.write_bytes(b"\xef\xbb\xbfusername;text\nann;\"one; two\"\n")
    con = connect()
    load(con, str(path))
    assert rows(con, "select username, text from comments") == [("ann", "one; two")]


def test_quoted_text_with_line_breaks_commas_and_quotes_is_one_row(tmp_path, make_csv):
    con = connect()
    text = 'first line\nsecond, with "quotes"'
    load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "text": text}]))
    assert rows(con, "select text from comments") == [(text,)]


def test_path_with_space_and_quote(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "it's a file.csv", [{"username": "ann", "text": "hi"}]))
    assert rows(con, "select count(*) from comments") == [(1,)]


def test_usernames_are_trimmed_and_rows_without_one_are_dropped(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": " ann ", "text": "a"}, {"username": "", "text": "b"}]))
    assert rows(con, "select username from comments") == [("ann",)]
    assert any("1" in w and "username" in w for w in warnings)


def test_timestamps_are_utc_and_bad_ones_become_null(tmp_path, make_csv):
    con = connect()
    stamps = ["2026-11-01T10:00:00", "2026-11-01T12:00:00+02:00", "2026-11-01T10:00:00Z", "not a date"]
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "timestamp": s} for s in stamps]))
    got = rows(con, "select strftime(timestamp, '%Y-%m-%dT%H:%M:%SZ') from comments order by comment_id::int")
    assert got == [("2026-11-01T10:00:00Z",)] * 3 + [(None,)]
    assert any("1" in w and "timestamp" in w for w in warnings)


def test_synthetic_flag(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": "a", "synthetic": "1"}, {"username": "b", "synthetic": "true"}, {"username": "c", "synthetic": ""}]))
    assert rows(con, "select synthetic from comments order by username") == [(True,), (True,), (False,)]


def test_profiles_keep_first_row_per_username(tmp_path, make_csv):
    con = connect()
    comments = make_csv(tmp_path, "c.csv", [{"username": "ann", "text": "hi"}])
    profiles = make_csv(tmp_path, "p.csv", [{"username": "ann", "label": "human", "created_at": "2020-01-01"},
                                            {"username": "ann", "label": "bot"}])
    warnings = load(con, comments, profiles)
    assert rows(con, "select username, label, strftime(created_at, '%Y-%m-%d') from profiles") == [("ann", "human", "2020-01-01")]
    assert any("ann" in w or "duplicate" in w.lower() for w in warnings)


def test_profile_file_without_username_is_ignored_with_a_warning(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann"}]), make_csv(tmp_path, "p.csv", [{"label": "bot"}]))
    assert rows(con, "select count(*) from profiles") == [(0,)]
    assert any("username" in w for w in warnings)


@pytest.mark.parametrize("content", ["", "username,text\n", "text\nhello\n"])
def test_unusable_comment_files_raise_input_error(tmp_path, content):
    path = tmp_path / "c.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(InputError):
        load(connect(), str(path))


def test_missing_file_raises_input_error(tmp_path):
    with pytest.raises(InputError):
        load(connect(), str(tmp_path / "nope.csv"))


def test_whitespace_only_cells_are_empty(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "text": "hi", "repost_of": " ", "parent_id": "\t"}]))
    assert rows(con, "select repost_of, parent_id from comments") == [(None, None)]
