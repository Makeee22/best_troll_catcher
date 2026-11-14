import json

from swarm import schemaorg
from swarm.convert import convert

URL = "https://forum.example/t/1"


def ld(*blocks):
    return "<html><head>" + "".join(f'<script type="application/ld+json">{b}</script>' for b in blocks) + "</head></html>"


def by_id(rows):
    return {r["comment_id"]: r for r in rows}


# Synthetic markup (hand-written, no real comments).
FORUM = json.dumps({
    "@context": "https://schema.org", "@type": "DiscussionForumPosting", "@id": "https://forum.example/t/1#post",
    "headline": "synthetic topic",
    "comment": [
        {"@type": "Comment", "@id": "c1", "text": "first", "dateCreated": "2026-11-14T10:00:00+00:00",
         "author": {"@type": "Person", "name": "Alice", "url": "https://forum.example/u/alice"},
         "comment": [{"@type": "Comment", "@id": "c2", "text": "a reply", "datePublished": "2026-11-14T10:05:00Z",
                      "author": {"@type": "Person", "name": "Bob", "identifier": "bob99"}}]},
        {"@type": "Comment", "text": "second", "author": "Carol"},
    ]})


def test_json_ld_forum_posting_with_nested_reply():
    rows = schemaorg.from_html(ld(FORUM), URL)
    got = by_id(rows)
    assert len(rows) == 3 and set(got) == {"c1", "c2", "sx2"}
    assert got["c1"]["username"] == "https://forum.example/u/alice" and got["c1"]["display_name"] == "Alice"
    assert got["c2"]["username"] == "bob99" and got["c2"]["parent_id"] == "c1"
    assert got["sx2"]["username"] == "Carol" and got["sx2"]["parent_id"] == ""
    assert {r["thread_id"] for r in rows} == {"https://forum.example/t/1#post"}
    assert got["c1"]["timestamp"] == "2026-11-14T10:00:00+00:00" and got["c2"]["timestamp"] == "2026-11-14T10:05:00Z"
    assert all(r["source"] == "thread" and r["text"] for r in rows)


def test_graph_review_list_author_list_and_field_preference():
    data = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "url": "https://shop.example"},
        {"@type": "Product", "url": "https://shop.example/p/1", "review": [
            {"@type": "Review", "reviewBody": "body", "description": "other", "author": [{"name": "Dan"}, {"name": "Eve"}]},
            {"@type": ["Thing", "Review"], "text": "t", "reviewBody": "b", "author": {"alternateName": "x"}},
            {"@type": "Review", "description": "only a description", "author": "Fay"}]}]}
    rows = schemaorg.from_html(ld(json.dumps(data)), URL)
    assert [r["text"] for r in rows] == ["body", "t", "only a description"]
    assert [r["username"] for r in rows] == ["Dan", "", "Fay"]  # an author with no name, url or identifier stays empty
    assert {r["thread_id"] for r in rows} == {"https://shop.example/p/1"}


def test_thread_falls_back_to_the_page_url_and_repeated_ids_do_not_collapse():
    data = [{"@type": "Review", "url": "https://shop.example/p/1", "reviewBody": "a", "author": "x"},
            {"@type": "Review", "url": "https://shop.example/p/1", "reviewBody": "b", "author": "y"}]
    rows = schemaorg.from_html(ld(json.dumps(data)), URL)
    assert [r["comment_id"] for r in rows] == ["https://shop.example/p/1", "sx1"]
    assert {r["thread_id"] for r in rows} == {URL}


MICRODATA = """
<div itemscope itemtype="https://schema.org/Product"><meta itemprop="url" content="https://shop.example/p/2">
  <div itemprop="review" itemscope itemtype="https://schema.org/Review" itemid="r1">
    <span itemprop="author" itemscope itemtype="https://schema.org/Person"><span itemprop="name">Gus</span>
      <a itemprop="url" href="https://shop.example/u/gus">profile</a></span>
    <time itemprop="datePublished" datetime="2026-11-14">14 Nov</time>
    <p itemprop="reviewBody">fine<br>product</p>
  </div>
  <div itemprop="review" itemscope itemtype="http://schema.org/Review">
    <span itemprop="author">Hana</span>
    <meta itemprop="datePublished" content="2026-11-13T08:00:00Z">
    <div itemprop="reviewBody">  second   one </div>
  </div>
</div>
<script>var x = '<div itemprop="reviewBody">not me</div>';</script>
"""


def test_microdata_review_list():
    rows = schemaorg.from_html(MICRODATA, URL)
    assert len(rows) == 2
    a, b = rows
    assert (a["comment_id"], a["username"], a["display_name"], a["timestamp"]) == ("r1", "https://shop.example/u/gus", "Gus", "2026-11-14")
    assert a["text"] == "fine\nproduct"
    assert (b["comment_id"], b["username"], b["text"], b["timestamp"]) == ("sx1", "Hana", "second one", "2026-11-13T08:00:00Z")
    assert {r["thread_id"] for r in rows} == {"https://shop.example/p/2"}


def test_microdata_nested_reply_without_itemprop_and_unclosed_tags():
    page = ('<div itemscope itemtype="https://schema.org/Comment" itemid="m1"><span itemprop="author">A</span>'
            '<p itemprop="text">top</p>'
            '<div itemscope itemtype="https://schema.org/Comment"><span itemprop="author">B</span><p itemprop="text">reply</div>'
            '</div>')
    rows = by_id(schemaorg.from_html(page, URL))
    assert rows["m1"]["text"] == "top" and rows["sx1"]["parent_id"] == "m1" and rows["sx1"]["text"] == "reply"


def test_bad_json_in_one_block_does_not_stop_the_others():
    page = ld("{not json", FORUM, "[1, 2", '{"@type": "Comment"')
    assert len(schemaorg.from_html(page, URL)) == 3


def test_no_markup_and_odd_shapes_give_no_rows_and_never_raise():
    assert schemaorg.from_html("", URL) == []
    assert schemaorg.from_html("<p>just text</p>", URL) == []
    for odd in ["null", "5", '"s"', "[]", '{"@type": "Comment"}', '{"@type": 7, "comment": [null, 3, {"@type": null}]}',
                '{"@type": "Comment", "author": [], "text": ["a"]}']:
        assert len(schemaorg.from_html(ld(odd), URL)) <= 1


def test_deep_nesting_does_not_recurse():
    deep = "[" * 100000 + "]" * 100000
    assert schemaorg.from_html(ld(deep), URL) == []  # the JSON parser gives up; the page is skipped
    depth = 400
    chain = '{"@type": "Comment", "text": "leaf", "author": "z"}'
    for _ in range(depth):
        chain = '{"@type": "Comment", "text": "n", "author": "z", "comment": ' + chain + "}"
    assert len(schemaorg.from_html(ld(chain), URL)) == depth + 1
    html = '<div itemscope itemtype="https://schema.org/Comment">' * 4000 + "x"
    assert len(schemaorg.from_html(html, URL)) == 4000


def test_comments_are_capped():
    data = json.dumps([{"@type": "Comment", "text": "t", "author": "a"}] * (schemaorg.MAX_COMMENTS + 10))
    assert len(schemaorg.from_html(ld(data), URL)) == schemaorg.MAX_COMMENTS


def test_convert_reads_schema_org_when_no_site_rule_applies():
    comments, _, _ = convert({"url": URL, "pages": [{"url": URL, "frames": [{"html": ld(FORUM)}]}]})
    assert len(comments) == 3


def test_opening_post_with_text_is_a_row_but_not_the_parent_of_comments():
    data = {"@type": "DiscussionForumPosting", "@id": "p1", "author": "Op", "text": "opening", "headline": "h",
            "comment": [{"@type": "Comment", "@id": "c1", "text": "first", "author": "A"}]}
    got = by_id(schemaorg.from_html(ld(json.dumps(data)), URL))
    assert got["p1"]["text"] == "opening" and got["p1"]["thread_id"] == "p1" and got["p1"]["parent_id"] == ""
    assert got["c1"]["parent_id"] == "" and got["c1"]["thread_id"] == "p1"


def test_json_ld_wins_when_the_page_also_has_microdata():
    page = ld(FORUM) + MICRODATA
    assert len(schemaorg.from_html(page, URL)) == 3
