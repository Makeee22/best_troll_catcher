from swarm import sites
from swarm.convert import convert, merge

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


def test_markup_after_an_unclosed_tag_does_not_leak_into_the_text():
    html = ('<shreddit-comment thingid="t1_a" author="alice" postid="t3_p">'
            '<div id="t1_a-comment-rtjson-content"><p>one<p>two</div><button>Reply</button><button>Share</button></shreddit-comment>'
            '<shreddit-comment thingid="t1_b" author="bob" postid="t3_p">'
            '<div id="t1_b-comment-rtjson-content"><p>next</p></div></shreddit-comment>')
    got = by_id(sites.from_html(html, "u")[0])
    assert got["a"]["text"] == "one\ntwo" and got["b"]["text"] == "next"


def test_footer_and_script_after_the_last_comment_do_not_leak_into_the_text():
    html = ('<body><shreddit-comment thingid="t1_a" author="alice" postid="t3_p">'
            '<div id="t1_a-comment-rtjson-content"><p>last<p>x</div></shreddit-comment>'
            '<footer>Terms Privacy Help</footer><script>var x=1;</script></body>')
    assert by_id(sites.from_html(html, "u")[0])["a"]["text"] == "last\nx"


# Synthetic Context.dev parser output (hand-written, no real reviews).
def parsed(kind, data):
    return {"type": kind, "success": True, "data": data}


def first(kind, data, url="u"):
    rows, profiles, warnings = sites.from_parsed(parsed(kind, data), url)
    r = rows[0]
    return (r["comment_id"], r["username"], r["display_name"], r["text"], r["timestamp"], r["thread_id"], r["source"]), rows, profiles, warnings


def names_only(kind):
    return f"converter: {kind} gives display names only: two people with the same name count as one account"


def test_google_maps_mapper():
    data = {"featureId": "0xf:0x1", "cid": "123", "reviews": [
        {"id": "r1", "snippet": "great", "isoDate": "2026-11-14T10:00:00Z", "user": {"name": "Ann", "link": "https://x/maps/contrib/1234567/reviews", "reviews": 12}},
        {"id": "r2", "isoDate": "2026-11-14T11:00:00Z", "user": {"name": "Bo", "reviews": 5}}]}
    row, rows, profiles, warnings = first("google-maps-reviews", data)
    assert row == ("r1", "1234567", "Ann", "great", "2026-11-14T10:00:00Z", "0xf:0x1", "thread")
    assert rows[1]["username"] == "Bo" and rows[1]["text"] == ""  # no link: the name; rating-only: no snippet
    assert profiles == [{"username": "1234567", "display_name": "Ann", "created_at": "", "post_count": "12"}]
    assert warnings == []
    assert sites.from_parsed(parsed("google-maps-reviews", {"cid": "9", "reviews": [{}]}), "u")[0][0]["thread_id"] == "9"


def test_app_store_mapper_warns_about_display_names():
    data = {"app_id": "42", "reviews": [{"id": "a1", "author": "Ann", "title": "Nice", "text": "works", "created_at": "2026-11-14T10:00:00Z"}, {}]}
    row, rows, _, warnings = first("app-store-reviews", data)
    assert row == ("a1", "Ann", "Ann", "Nice\nworks", "2026-11-14T10:00:00Z", "42", "thread")
    assert rows[1]["text"] == "" and rows[1]["username"] == ""
    assert warnings == [names_only("app-store-reviews")]


def test_google_play_mapper_warns_about_display_names():
    data = {"app_id": "com.x", "reviews": [{"id": "p1", "author": "Ann", "text": "ok", "created_at": "2026-11-14T10:00:00Z"}]}
    row, _, _, warnings = first("google-play-reviews", data)
    assert row == ("p1", "Ann", "Ann", "ok", "2026-11-14T10:00:00Z", "com.x", "thread")
    assert warnings == [names_only("google-play-reviews")]


def test_tripadvisor_mapper():
    data = {"location": {"id": "L1"}, "reviews": [
        {"id": "t1", "title": "Nice", "text": "stay", "published_at": "2026-11-14T10:00:00Z", "author": {"username": "ann_u", "id": "A1", "name": "Ann", "contribution_count": 7}},
        {"id": "t2", "text": "x", "author": {"id": "A2", "name": "Bo"}}]}
    row, rows, profiles, warnings = first("tripadvisor-reviews", data)
    assert row == ("t1", "ann_u", "Ann", "Nice\nstay", "2026-11-14T10:00:00Z", "L1", "thread")
    assert rows[1]["username"] == "A2" and rows[1]["text"] == "x"  # no title: no stray newline
    assert profiles == [{"username": "ann_u", "display_name": "Ann", "created_at": "", "post_count": "7"}]
    assert warnings == []


def test_yelp_mapper():
    data = {"business": {"id": "B1"}, "reviews": [
        {"id": "y1", "text": "tasty", "updated_at": "2026-11-14T10:00:00Z", "author": {"id": "Y1", "name": "Ann", "review_count": 3}}, {}]}
    row, rows, profiles, warnings = first("yelp-reviews", data)
    assert row == ("y1", "Y1", "Ann", "tasty", "2026-11-14T10:00:00Z", "B1", "thread")
    assert rows[1]["username"] == "" and rows[1]["text"] == ""
    assert profiles == [{"username": "Y1", "display_name": "Ann", "created_at": "", "post_count": "3"}]
    assert warnings == []


def test_g2_mapper_joins_parts_and_warns():
    data = {"product": {"slug": "acme"}, "reviews": [
        {"id": "g1", "likes": "fast", "dislikes": "", "problems_solved": "reports", "published_at": "2026-11-14T10:00:00Z", "reviewer": {"name": "Ann"}},
        {"id": "g2", "likes": "ok", "reviewer": {"name": "Verified User in Computer Software"}}]}
    row, rows, _, warnings = first("g2-reviews", data)
    assert row == ("g1", "Ann", "Ann", "fast\nreports", "2026-11-14T10:00:00Z", "acme", "thread")
    assert rows[1]["username"] == "Verified User in Computer Software"  # mapped as is: the merge drops it
    assert warnings == [names_only("g2-reviews")]
    comments, _, notes = convert({"url": "u", "pages": [{"url": "u", "role": "thread", "parsed": parsed("g2-reviews", data)}]})
    assert [c["username"] for c in comments] == ["Ann"]
    assert any("anonymous" in n for n in notes)


def test_tiktok_mapper_takes_the_video_id_from_the_page_url():
    data = {"comments": [{"id": "k1", "text": "hi", "posted_at": "2026-11-14T10:00:00Z", "author": {"username": "ann", "nickname": "Ann"}}, {}]}
    row, rows, _, warnings = first("tiktok-comments", data, "https://www.tiktok.com/@someone/video/7106594312292453675")
    assert row == ("k1", "ann", "Ann", "hi", "2026-11-14T10:00:00Z", "7106594312292453675", "thread")
    assert rows[1]["thread_id"] == "7106594312292453675" and rows[1]["text"] == ""
    assert warnings == []
    assert first("tiktok-comments", data, "https://www.tiktok.com/@someone")[0][5] == ""


def test_every_mapper_survives_empty_data():
    for kind in sites.MAPPERS:
        assert sites.from_parsed(parsed(kind, {}), "u")[0] == []
        assert sites.from_parsed({"type": kind, "success": True}, "u")[0] == []
        assert sites.from_parsed(parsed(kind, ["not", "a", "dict"]), "u")[0] == []


def test_malformed_items_and_values_do_not_crash_or_hide_the_good_rows():
    good_user = {"id": "ok", "text": "fine", "author": {"id": "u1", "username": "u1", "name": "U"}, "user": {"name": "U"}, "reviewer": {"name": "U"}}
    for kind in ("google-maps-reviews", "tripadvisor-reviews", "yelp-reviews", "g2-reviews", "tiktok-comments",
                 "app-store-reviews", "google-play-reviews"):
        key = "comments" if kind == "tiktok-comments" else "reviews"
        for bad in ({"reviews": "x", "comments": "x"}, {"reviews": {"a": 1}, "comments": {"a": 1}}, {"reviews": None, "comments": None}):
            assert sites.from_parsed(parsed(kind, bad), "u")[0] == []
        data = {key: [None, "str", 5, {"id": "b", "author": None, "user": "x", "reviewer": ["x"], "likes": 5, "dislikes": ["a"],
                                       "problems_solved": {"a": 1}, "text": 7, "title": None, "snippet": 3}, good_user],
                "product": "x", "location": 5, "business": [], "app_id": None}
        rows = sites.from_parsed(parsed(kind, data), "u")[0]
        assert [r["comment_id"] for r in rows] == ["b", "ok"]  # non-dict items skipped, odd values read as empty
        assert all(isinstance(v, str) for r in rows for v in r.values())


def test_g2_numbers_in_text_fields_are_joined_as_text():
    data = {"reviews": [{"reviewer": {"name": "Ann"}, "likes": 5, "dislikes": "bad"}]}
    assert sites.from_parsed(parsed("g2-reviews", data), "u")[0][0]["text"] == "5\nbad"


def test_google_user_placeholder_leaves_no_profile():
    data = {"featureId": "f", "reviews": [{"id": "r", "snippet": "text", "user": {"name": "A Google user", "reviews": 3}}]}
    rows, profiles, _ = sites.from_parsed(parsed("google-maps-reviews", data), "u")
    assert merge(rows, profiles)[1] == []
