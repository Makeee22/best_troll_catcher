from swarm import sites
from swarm.convert import convert

# Synthetic page in the shape of a saved Reddit thread (hand-written, no real comments).
THREAD = """
<html><body>
<shreddit-post id="t3_post1" author="op_user" post-title="A title" subreddit-prefixed-name="r/test"
    created-timestamp="2026-11-14T09:00:00.000000+0000" comment-count="5">
  <div id="t3_post1-post-rtjson-content"><p>post body</p></div>
</shreddit-post>
<shreddit-comment thingid="t1_c1" author="alice" created="2026-11-14T10:00:00.000000+0000"
    parentid="" postid="t3_post1" depth="0">
  <div id="t1_c1-comment-rtjson-content"><p>first</p><p>line two</p></div>
  <shreddit-comment thingid="t1_c2" author="bob" created="2026-11-14T10:05:00.000000+0000"
      parentid="t1_c1" postid="t3_post1" depth="1">
    <div id="t1_c2-comment-rtjson-content"><blockquote><p>quoted parent</p></blockquote><p>my answer</p></div>
  </shreddit-comment>
</shreddit-comment>
<shreddit-comment thingid="t1_c3" author="carol" created="2026-11-14T10:10:00.000000+0000"
    parentid="t3_post1" postid="t3_post1" depth="0">
  <div id="t1_c3-comment-rtjson-content">line<br>break</div>
</shreddit-comment>
</body></html>
"""


def by_id(rows):
    return {r["comment_id"]: r for r in rows}


def test_thread_page_rows_ids_quote_and_coverage():
    rows, profiles, warnings = sites.from_html(THREAD, "https://www.reddit.com/r/test/comments/post1/")
    got = by_id(rows)
    assert set(got) == {"post1", "c1", "c2", "c3"}
    assert all(r["source"] == "thread" for r in rows)
    assert got["c2"]["text"] == "my answer"
    assert got["c2"]["parent_id"] == "c1"
    assert got["c1"]["text"] == "first\nline two"
    assert got["c3"]["text"] == "line\nbreak"  # <br> is void: it must not leave the text element open
    assert got["c3"]["parent_id"] == "post1"
    assert got["c1"]["timestamp"] == "2026-11-14T10:00:00Z" and got["c1"]["username"] == "alice"
    assert got["post1"]["thread_id"] == "post1" and got["post1"]["text"] == "post body" and got["post1"]["username"] == "op_user"
    assert {r["thread_id"] for r in rows} == {"post1"}
    assert profiles == []
    assert warnings == ["converter: read 3 of 5 comments on the Reddit thread (the rest were not loaded on the saved page)"]


def test_post_without_a_body_gives_no_row_and_full_page_no_warning():
    html = '<shreddit-post id="t3_p" author="a" comment-count="1"></shreddit-post>' \
           '<shreddit-comment thingid="t1_x" author="alice" postid="t3_p" parentid="t3_p">' \
           '<div id="t1_x-comment-rtjson-content">hi</div></shreddit-comment>'
    rows, _, warnings = sites.from_html(html, "u")
    assert [r["comment_id"] for r in rows] == ["x"] and warnings == []


def test_html_without_shreddit_elements_is_empty():
    assert sites.from_html("<p>hello</p>", "u") == ([], [], [])


def test_convert_reads_a_saved_thread_page():
    comments, _, warnings = convert({"url": "u", "pages": [{"url": "u", "role": "thread", "html": THREAD}]})
    assert sorted(c["comment_id"] for c in comments) == ["c1", "c2", "c3", "post1"]
    assert any("3 of 5" in w for w in warnings)


def reddit_user(comments):
    return {"type": "reddit-user", "success": True,
            "data": {"user": {"username": "alice", "created_at": "2015-01-01T00:00:00Z"}, "comments": comments}}


def test_reddit_user_mapper():
    parsed = reddit_user([
        {"id": "19ruo33ofgh8i", "body": "one", "posted_at": "2026-11-14T10:00:00Z", "parent_id": None, "post": {"id": "t3_p1"}},
        {"id": "19ruzzz", "body": "two", "posted_at": "2026-11-14T11:00:00Z", "parent_id": "19ruo33ofgh8i", "post": {"id": "t3_p1"}},
    ])
    rows, profiles, warnings = sites.from_parsed(parsed, "u")
    assert [(r["comment_id"], r["username"], r["text"], r["timestamp"], r["parent_id"], r["thread_id"], r["source"]) for r in rows] == [
        ("19ruo33ofgh8i", "alice", "one", "2026-11-14T10:00:00Z", "", "p1", "history"),
        ("19ruzzz", "alice", "two", "2026-11-14T11:00:00Z", "19ruo33ofgh8i", "p1", "history")]
    assert profiles == [{"username": "alice", "display_name": "", "created_at": "2015-01-01T00:00:00Z", "post_count": ""}]
    assert warnings == []


def test_reddit_user_mapper_survives_missing_keys():
    rows, profiles, _ = sites.from_parsed({"type": "reddit-user", "success": True, "data": {"comments": [{}]}}, "u")
    assert len(rows) == 1 and rows[0]["comment_id"] == "" and rows[0]["thread_id"] == ""
    assert profiles[0]["username"] == ""


def test_unknown_parser_and_failed_parser_warn():
    assert sites.from_parsed({"type": "mystery", "success": True}, "u") == ([], [], ["converter: no mapper for parser mystery"])
    failed = {"type": "reddit-user", "success": False, "error_code": "BLOCKED"}
    assert sites.from_parsed(failed, "u") == ([], [], ["converter: Context.dev parser reddit-user failed: BLOCKED"])


def test_unclosed_tag_in_a_comment_does_not_swallow_the_next_comment():
    html = ('<shreddit-comment thingid="t1_a" author="alice" postid="t3_p" parentid="t3_p">'
            '<div id="t1_a-comment-rtjson-content"><p>one<p>two</div></shreddit-comment>'
            '<shreddit-comment thingid="t1_b" author="bob" postid="t3_p" parentid="t3_p">'
            '<div id="t1_b-comment-rtjson-content"><p>next</p></div></shreddit-comment>')
    got = by_id(sites.from_html(html, "u")[0])
    assert got["a"]["text"] == "one\ntwo" and got["b"]["text"] == "next"


def test_truncated_page_keeps_the_last_comment_text():
    html = '<shreddit-comment thingid="t1_a" author="alice" postid="t3_p"><div id="t1_a-comment-rtjson-content"><p>cut off'
    assert by_id(sites.from_html(html, "u")[0])["a"]["text"] == "cut off"
