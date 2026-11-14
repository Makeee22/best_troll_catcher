"""swarm.collect: offline only. Every response below is hand-written and synthetic (no real accounts)."""
import json
import subprocess
import sys
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest

from swarm import collect as collect_module
from swarm.collect import CollectError, collect, contextdev, run
from swarm.convert import convert

BSKY_API = "https://public.api.bsky.app/xrpc/"
VISIBLE = "app.bsky.feed.defs#threadViewPost"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """A missed fake must fail loudly, not fetch."""
    def no_network(*a, **k):
        raise AssertionError("network access in a test")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(contextdev.time, "sleep", lambda s: None)
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)


class FakeClient:
    """The client interface the collectors use. routes: callables url -> response."""
    workers = 2

    def __init__(self, json_routes=None, direct_routes=None, html=None, parsed=None):
        self.json_routes = json_routes or (lambda url: None)
        self.direct_routes = direct_routes or (lambda url: None)
        self.html, self.parsed = html, parsed
        self.credits_used, self.credits_remaining = 0, None
        self.calls = []

    def fetch_json(self, url):
        self.calls.append(("json", url))
        self.credits_used += 1
        return self.json_routes(url), "context.dev"

    def direct_json(self, url):
        self.calls.append(("direct", url))
        data = self.direct_routes(url)
        if data is None:
            raise CollectError("The site answered 404")
        return data

    def fetch_html(self, url, wait_ms=6000, must_contain=None, tries=2):
        self.calls.append(("html", url))
        return self.html

    def parse(self, url, parser, limit=None):
        self.calls.append(("parse", url, parser, limit))
        self.credits_used += 1
        return self.parsed(url, parser) if callable(self.parsed) else self.parsed


# --- Bluesky ---------------------------------------------------------------------------------

def bpost(name, text, n, parent=None, root=None, replies=0, handle=None, created="2026-11-14T10:00:00Z"):
    uri = f"at://did:plc:{name}/app.bsky.feed.post/{n}"
    rec = {"text": text, "createdAt": created}
    if parent:
        rec["reply"] = {"parent": {"uri": parent}, "root": {"uri": root or parent}}
    return {"uri": uri, "author": {"did": f"did:plc:{name}", "handle": handle or f"{name}.example.test", "displayName": name.title()},
            "record": rec, "replyCount": replies, "indexedAt": created}


ROOT = bpost("rootuser", "A synthetic root post", "r1", replies=3)
R1 = bpost("alice", "first reply text here", "a1", ROOT["uri"], replies=1)
R2 = bpost("bob", "second reply text here", "b1", ROOT["uri"])
R11 = bpost("carol", "nested reply text here", "c1", R1["uri"], ROOT["uri"], handle="handle.invalid")
THREAD = {"thread": {"$type": VISIBLE, "post": ROOT, "replies": [
    {"$type": VISIBLE, "post": R1, "replies": [{"$type": VISIBLE, "post": R11, "replies": []}]},
    {"$type": VISIBLE, "post": R2, "replies": []},
    {"$type": "app.bsky.feed.defs#blockedPost", "uri": "at://blocked"},
]}}


def bluesky_routes(fail=()):
    def route(url):
        u = urlparse(url)
        q = parse_qs(u.query)
        method = u.path.rsplit("/", 1)[-1]
        if method == "com.atproto.identity.resolveHandle":
            return {"did": "did:plc:rootuser"}
        if method == "app.bsky.feed.getPostThread":
            assert q["depth"] == ["1000"] and q["parentHeight"] == ["0"]
            return THREAD
        if method == "app.bsky.feed.getAuthorFeed":
            did = q["actor"][0]
            if did in fail:
                raise CollectError("boom")
            assert q["filter"] == ["posts_with_replies"]
            mine = [p for p in (ROOT, R1, R2, R11) if p["author"]["did"] == did]
            reposted = {"post": bpost("elsewhere", "reposted text", "e1"), "reason": {"$type": "app.bsky.feed.defs#reasonRepost", "indexedAt": "2026-11-13T10:00:00Z", "by": mine[0]["author"]}}
            return {"feed": [{"post": p} for p in mine] + [reposted], "limit": q["limit"][0]}
        if method == "app.bsky.actor.getProfiles":
            return {"profiles": [{"did": d, "handle": "handle.invalid" if d.endswith("carol") else f"{d[8:]}.example.test", "createdAt": "2024-01-01T00:00:00Z", "postsCount": 7}
                                 for d in q["actors"]]}
        raise AssertionError(url)
    return route


POST_LINK = "https://bsky.app/profile/rootuser.example.test/post/r1"


def test_unsupported_site():
    with pytest.raises(CollectError, match="not supported yet"):
        collect("https://example.test/some/page", client=FakeClient())


def test_bluesky_bundle_keeps_the_thread_unchanged_and_fetches_histories_directly():
    progress = []
    client = FakeClient(bluesky_routes(), bluesky_routes())
    bundle = collect(POST_LINK, history=5, on_progress=lambda d, t: progress.append((d, t)), client=client)
    assert bundle["site"] == "bluesky" and bundle["url"] == POST_LINK and bundle["collected_at"].endswith("Z")
    pages = bundle["pages"]
    assert pages[0]["role"] == "thread" and pages[0]["json"] == THREAD
    feeds = [p for p in pages if "feed" in p.get("json", {})]
    profile_pages = [p for p in pages if "profiles" in p.get("json", {})]
    assert len(feeds) == 4 and all(p["role"] == "profile" for p in feeds + profile_pages)
    assert [len(p["json"]["profiles"]) for p in profile_pages] == [4]
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
    feeds_called = [c for c in client.calls if "getAuthorFeed" in c[1]]
    assert feeds_called and all(c[0] == "direct" and "limit=100" in c[1] for c in feeds_called)   # a window: read 100, keep 5
    t = bundle["thread"]
    assert (t["platform"], t["post_id"], t["commenters"], t["commenters_fetched"], t["history_per_commenter"]) == \
        ("Bluesky", ROOT["uri"], 4, 4, 5)
    assert (t["histories_ok"], t["histories_failed"]) == (4, 0)
    cov = bundle["coverage"]
    assert cov["comments_found"] == 3 and cov["comments_expected"] == 4     # sum of replyCount: 3 + 1
    assert any("1 could not be" in n or "does not return the other" in n for n in cov["notes"])
    assert bundle["credits_used"] == sum(c[0] == "json" for c in client.calls)


def test_bluesky_participant_cap_and_failed_histories_are_noted_and_skipped():
    client = FakeClient(bluesky_routes(fail={"did:plc:bob"}), bluesky_routes(fail={"did:plc:bob"}))
    bundle = collect(POST_LINK, history=5, max_participants=3, client=client)
    t = bundle["thread"]
    assert (t["commenters"], t["commenters_fetched"], t["histories_ok"], t["histories_failed"]) == (4, 3, 2, 1)
    assert sum(1 for p in bundle["pages"] if "feed" in p.get("json", {})) == 2
    notes = " ".join(bundle["coverage"]["notes"])
    assert "3 most active" in notes and "1 participants could not be fetched" in notes


def test_bluesky_post_not_found():
    def route(url):
        if "resolveHandle" in url:
            return {"did": "did:plc:rootuser"}
        return {"thread": {"$type": "app.bsky.feed.defs#notFoundPost"}}
    with pytest.raises(CollectError, match="not found, or it is not public"):
        collect(POST_LINK, client=FakeClient(route))


def test_bluesky_bundle_converts_and_broken_handles_become_the_did():
    bundle = collect(POST_LINK, history=5, client=FakeClient(bluesky_routes(), bluesky_routes()))
    comments, profiles, _ = convert(bundle)
    names = {c["username"] for c in comments}
    assert "did:plc:carol" in names and "alice.example.test" in names
    assert any(c["repost_of"] for c in comments)
    assert {p["created_at"] for p in profiles} == {"2024-01-01T00:00:00Z"}


def test_run_gives_the_result_a_readable_label_and_puts_coverage_first():
    result, bundle = run(POST_LINK, similar_text=False, history=5, client=FakeClient(bluesky_routes()))
    assert result["source"]["comments_file"] == f"Bluesky thread {ROOT['uri']}"
    assert result["source"]["accounts"] == 4
    assert any("does not return the other" in w for w in result["warnings"][:3])
    assert bundle["pages"][0]["role"] == "thread"


def test_bluesky_without_a_key_uses_the_public_api_directly(monkeypatch):
    routes = bluesky_routes()
    monkeypatch.setattr(contextdev, "direct_json", routes)
    bundle = collect(POST_LINK, history=5)      # no client, no CONTEXT_DEV_API_KEY
    assert bundle["credits_used"] == 0 and bundle["thread"]["commenters"] == 4
    assert bundle["thread"]["via"] == {"direct": bundle["thread"]["via"]["direct"]}


def test_client_without_a_key_refuses_what_needs_one():
    client = contextdev.ContextDev("")
    with pytest.raises(CollectError, match="CONTEXT_DEV_API_KEY"):
        client.fetch_html("https://example.test/")


def test_fetch_json_falls_back_to_a_direct_request(monkeypatch):
    client = contextdev.ContextDev("not-a-real-key")
    monkeypatch.setattr(client, "_post", lambda *a, **k: {"_http_error": 500})
    monkeypatch.setattr(contextdev, "direct_json", lambda url: {"ok": 1})
    assert client.fetch_json("https://example.test/x") == ({"ok": 1}, "direct")


def test_the_core_does_not_import_the_collector():
    code = "import sys, swarm.core, swarm.detect; sys.exit(1 if any(m.startswith('swarm.collect') for m in sys.modules) else 0)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


# --- command line ----------------------------------------------------------------------------

def test_cli_writes_bundle_csvs_and_result_and_prints_a_summary(tmp_path, monkeypatch, capsys):
    from swarm.collect import __main__ as cli
    seen = {}

    def fake_collect(url, **options):
        seen.update(options)
        return collect(url, client=FakeClient(bluesky_routes()), **options)
    monkeypatch.setattr(cli, "collect", fake_collect)
    out = tmp_path / "out"
    assert cli.main([POST_LINK, str(out), "--history", "5", "--max-participants", "3", "--no-similar-text"]) == 0
    assert (seen["history"], seen["max_participants"]) == (5, 3)
    assert {p.name for p in out.iterdir()} == {"bundle.json", "comments.csv", "profiles.csv", "result.json"}
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["source"]["comments_file"].startswith("Bluesky thread at://")
    text = capsys.readouterr().out
    assert "comments from" in text and "clusters" in text


def test_cli_errors_are_one_line_and_exit_2(tmp_path, capsys):
    from swarm.collect import __main__ as cli
    assert cli.main(["https://example.test/x", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("error: This site is not supported yet")


# --- Hacker News -----------------------------------------------------------------------------

def hn(i, author, text, children=(), **extra):
    return {"id": i, "author": author, "text": text, "created_at": f"2026-11-14T10:{i % 60:02d}:00.000Z", "type": "comment",
            "parent_id": 1, "story_id": 1, "children": list(children), **extra}


HN_ITEM = {"id": 1, "author": "poster", "title": "A synthetic story", "url": "https://example.test/story", "text": None,
           "type": "story", "created_at": "2026-11-14T09:00:00.000Z", "parent_id": None, "story_id": 1, "children": [
               hn(2, "ann", "<p>first comment</p>", [hn(3, "ben", "nested comment"), hn(4, None, None)]),
               hn(5, "ann", "second comment by ann"),
               hn(6, "cy", "third comment")]}
HN_LINK = "https://news.ycombinator.com/item?id=1"


def hn_routes(fail=()):
    def route(url):
        u = urlparse(url)
        if u.path == "/api/v1/items/1":
            return HN_ITEM
        if u.path == "/api/v1/items/404":
            return None
        if u.path == "/api/v1/search_by_date":
            tags = parse_qs(u.query)["tags"][0]
            assert tags.startswith("comment,author_") and parse_qs(u.query)["hitsPerPage"] == ["5"]
            name = tags.split("author_")[1]
            if name in fail:
                return None
            return {"hits": [{"objectID": f"9{name}", "author": name, "comment_text": f"older words by {name}", "story_id": 1,
                              "created_at": "2026-11-01T10:00:00.000Z"}]}
        raise AssertionError(url)
    return route


def test_hn_bundle_uses_the_public_api_directly_never_context_dev():
    progress = []
    client = FakeClient(direct_routes=hn_routes())
    bundle = collect(HN_LINK, history=5, on_progress=lambda d, t: progress.append((d, t)), client=client)
    assert bundle["site"] == "hackernews" and bundle["credits_used"] == 0
    assert all(c[0] == "direct" for c in client.calls)
    assert bundle["pages"][0]["role"] == "thread" and bundle["pages"][0]["json"] == HN_ITEM
    hits = [p for p in bundle["pages"][1:] if "hits" in p["json"]]
    assert len(hits) == 4 and all(p["role"] == "profile" for p in hits)      # poster, ann, ben, cy
    assert progress[-1] == (4, 4)
    t = bundle["thread"]
    assert (t["platform"], t["post_id"], t["title"], t["commenters"], t["commenters_fetched"]) == \
        ("Hacker News", "1", "A synthetic story", 4, 4)
    assert bundle["coverage"]["comments_found"] == 4       # five comment nodes, one of them deleted
    assert bundle["coverage"]["comments_expected"] is None
    assert any("1 deleted" in n for n in bundle["coverage"]["notes"])


def test_hn_failed_history_is_skipped_and_noted_and_bundle_converts():
    bundle = collect(HN_LINK, history=5, client=FakeClient(direct_routes=hn_routes(fail={"cy"})))
    assert bundle["thread"]["histories_ok"] == 3 and bundle["thread"]["histories_failed"] == 1
    assert any("1 commenters could not be fetched" in n for n in bundle["coverage"]["notes"])
    comments, _, _ = convert(bundle)
    assert {c["username"] for c in comments} == {"poster", "ann", "ben", "cy"}
    assert not any(c["comment_id"] == "9cy" for c in comments)
    assert any(c["comment_id"] == "9ann" for c in comments)


def test_hn_item_not_found():
    with pytest.raises(CollectError, match="Hacker News"):
        collect("https://news.ycombinator.com/item?id=404", client=FakeClient(direct_routes=hn_routes()))


def test_hn_link_forms():
    from swarm.collect import hackernews
    assert hackernews.matches("https://news.ycombinator.com/item?id=4123456")
    assert hackernews.matches("https://news.ycombinator.com/item?id=4123456&p=2")
    assert not hackernews.matches("https://news.ycombinator.com/news")
    assert not hackernews.matches("https://news.ycombinator.com/item?id=abc")


# --- Reddit ----------------------------------------------------------------------------------

REDDIT_PAGE = """
<shreddit-post id="t3_post1" author="op_user" post-title="A synthetic title" subreddit-prefixed-name="r/test"
    created-timestamp="2026-11-14T09:00:00.000000+0000" comment-count="5"></shreddit-post>
<shreddit-comment thingid="t1_c1" author="alice" created="2026-11-14T10:00:00.000000+0000" parentid="" postid="t3_post1">
  <div id="t1_c1-comment-rtjson-content"><p>first comment</p></div></shreddit-comment>
<shreddit-comment thingid="t1_c2" author="bob_b" created="2026-11-14T10:05:00.000000+0000" parentid="t1_c1" postid="t3_post1">
  <div id="t1_c2-comment-rtjson-content"><p>a reply</p></div></shreddit-comment>
<shreddit-comment thingid="t1_c3" author="[deleted]" created="2026-11-14T10:06:00.000000+0000" parentid="t1_c1" postid="t3_post1">
  <div id="t1_c3-comment-rtjson-content"><p>gone</p></div></shreddit-comment>
<shreddit-comment thingid="t1_c4" author="x" created="2026-11-14T10:07:00.000000+0000" parentid="t1_c1" postid="t3_post1">
  <div id="t1_c4-comment-rtjson-content"><p>too short a name for reddit</p></div></shreddit-comment>
"""
REDDIT_LINK = "https://www.reddit.com/r/test/comments/post1/a_synthetic_title/"


def reddit_user(name, fail=()):
    def parsed(url, parser):
        assert parser == "reddit-user" and f"/user/{name}/" in url
        if name in fail:
            return {"type": parser, "success": False, "error_code": "BLOCKED"}
        return {"type": parser, "success": True, "data": {"user": {"username": name, "created_at": "2020-05-05T00:00:00Z"},
                "comments": [{"id": "19r" + name, "body": f"earlier words by {name}", "posted_at": "2026-11-01T10:00:00Z",
                              "parent_id": "19rxyz", "post": {"id": "other"}}]}}
    return parsed


def reddit_client(fail=(), html=REDDIT_PAGE):
    def parsed(url, parser):
        name = url.split("/user/")[1].split("/")[0]
        return reddit_user(name, fail)(url, parser)
    return FakeClient(html=html, parsed=parsed)


def test_reddit_thread_page_and_histories_as_parsed_exactly_as_returned():
    progress = []
    client = reddit_client()
    bundle = collect(REDDIT_LINK, history=7, on_progress=lambda d, t: progress.append((d, t)), client=client)
    assert bundle["site"] == "reddit"
    assert bundle["pages"][0]["role"] == "thread" and bundle["pages"][0]["html"] == REDDIT_PAGE
    profiles = bundle["pages"][1:]
    assert [p["parsed"]["data"]["user"]["username"] for p in profiles] == ["alice", "bob_b"]   # not [deleted], not 'x'
    assert all(p["role"] == "profile" and p["url"].startswith("https://www.reddit.com/user/") for p in profiles)
    assert [c[2:] for c in client.calls if c[0] == "parse"] == [("reddit-user", 7)] * 2
    assert progress == [(1, 2), (2, 2)]
    t = bundle["thread"]
    assert (t["platform"], t["title"], t["post_id"], t["commenters"], t["commenters_fetched"]) == \
        ("Reddit", "A synthetic title", "post1", 3, 2)         # three authors; 'x' is not a valid Reddit name
    assert (bundle["coverage"]["comments_found"], bundle["coverage"]["comments_expected"]) == (3, 5)
    comments, prof, _ = convert(bundle)
    assert {c["comment_id"] for c in comments} >= {"c1", "c2", "19ralice", "19rbob_b"}
    assert {p["created_at"] for p in prof if p["username"] == "alice"} == {"2020-05-05T00:00:00Z"}


def test_reddit_failed_history_is_skipped_and_noted():
    bundle = collect(REDDIT_LINK, client=reddit_client(fail={"bob_b"}))
    assert (bundle["thread"]["histories_ok"], bundle["thread"]["histories_failed"]) == (1, 1)
    assert len(bundle["pages"]) == 2
    assert any("1 commenters could not be fetched" in n for n in bundle["coverage"]["notes"])


def test_reddit_bot_check_page_is_an_error_not_a_crash():
    with pytest.raises(CollectError, match="bot check"):
        collect(REDDIT_LINK, client=FakeClient(html=""))
    with pytest.raises(CollectError, match="No comments"):
        collect(REDDIT_LINK, client=FakeClient(html="<shreddit-post id='t3_p'></shreddit-post>"))


def test_reddit_needs_a_key():
    with pytest.raises(CollectError, match="CONTEXT_DEV_API_KEY"):
        collect(REDDIT_LINK)


def test_reddit_link_forms():
    from swarm.collect import reddit
    assert reddit.matches("https://www.reddit.com/r/test/comments/post1/a_title/")
    assert reddit.matches("https://old.reddit.com/r/test/comments/post1/")
    assert not reddit.matches("https://www.reddit.com/r/test/")
    assert not reddit.matches("https://example.test/r/x/comments/abc")


# --- Context.dev review and comment parsers --------------------------------------------------

REVIEW_LINKS = {
    "https://www.google.com/maps/place/Some+Place/@60.1,24.9,17z": ("google-maps-reviews", 200),
    "https://apps.apple.com/us/app/some-app/id1000000000": ("app-store-reviews", None),
    "https://play.google.com/store/apps/details?id=com.example.app": ("google-play-reviews", None),
    "https://www.tripadvisor.com/Attraction_Review-g1-d2-Reviews-Some_Place-City.html": ("tripadvisor-reviews", None),
    "https://www.yelp.com/biz/some-place-city": ("yelp-reviews", None),
    "https://www.g2.com/products/some-product/reviews": ("g2-reviews", None),
    "https://www.tiktok.com/@someone/video/7000000000000000000": ("tiktok-comments", None),
}


@pytest.mark.parametrize("link,expected", REVIEW_LINKS.items())
def test_review_site_calls_its_parser_and_keeps_parsed_unchanged(link, expected):
    parser, limit = expected
    data = {"reviews": [{"author": "A Person", "text": "synthetic review"}] * 3, "location": {"review_count": 10}}
    parsed = {"requested": True, "success": True, "data": data, "type": parser}
    client = FakeClient(parsed=parsed)
    bundle = collect(link, client=client)
    assert client.calls == [("parse", link, parser, limit)]
    assert bundle["site"] == parser and bundle["pages"] == [{"url": link, "role": "thread", "parsed": parsed}]
    assert bundle["pages"][0]["parsed"] is parsed
    assert (bundle["coverage"]["comments_found"], bundle["coverage"]["comments_expected"]) == (3, 10)
    assert any("3 of 10" in n for n in bundle["coverage"]["notes"])
    assert bundle["credits_used"] == 1


def test_review_parser_failure_is_a_clear_error():
    failed = {"type": "yelp-reviews", "success": False, "error_code": "BLOCKED"}
    with pytest.raises(CollectError, match="BLOCKED"):
        collect("https://www.yelp.com/biz/some-place-city", client=FakeClient(parsed=failed))


def test_review_bundle_converts_and_runs():
    parsed = {"success": True, "type": "google-maps-reviews", "data": {"featureId": "f1", "reviews": [
        {"user": {"name": "Alice Example", "link": "https://www.google.com/maps/contrib/111"},
         "snippet": "synthetic words about the place", "isoDate": "2026-11-01T10:00:00Z"},
        {"user": {"name": "Bob Example", "link": "https://www.google.com/maps/contrib/222"},
         "snippet": "other synthetic words here", "isoDate": "2026-11-02T10:00:00Z"}]}}
    link = "https://www.google.com/maps/place/Some+Place/@60.1,24.9,17z"
    comments, _, _ = convert(collect(link, client=FakeClient(parsed=parsed)))
    assert len(comments) == 2


def test_other_links_on_review_sites_are_unsupported():
    for link in ("https://www.yelp.com/", "https://www.g2.com/categories/crm", "https://apps.apple.com.example.test/app/x"):
        with pytest.raises(CollectError, match="not supported yet"):
            collect(link, client=FakeClient())


# --- bad answers, limits and fallbacks (final review) ----------------------------------------

class _Body:
    def __init__(self, data=b"{}", error=None):
        self._data, self._error = data, error

    def read(self, *a):
        if self._error:
            raise self._error
        return self._data

    def close(self):   # HTTPError closes the body it wraps
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _answers(monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: body)


import http.client

BAD_BODIES = [_Body(b"<html>maintenance</html>"), _Body(b"[1, 2]"), _Body(error=http.client.IncompleteRead(b"{")),
              _Body(error=ConnectionResetError("reset"))]


@pytest.mark.parametrize("body", BAD_BODIES)
def test_direct_json_turns_a_bad_answer_into_a_collect_error(monkeypatch, body):
    _answers(monkeypatch, body)
    with pytest.raises(CollectError):
        contextdev.direct_json("https://example.test/x")


@pytest.mark.parametrize("body", BAD_BODIES)
def test_post_survives_a_bad_answer(monkeypatch, body):
    _answers(monkeypatch, body)
    out = contextdev.ContextDev("not-a-real-key")._post({"url": "https://example.test/"}, patient=False)
    assert out["_http_error"] is not None


def test_post_ignores_odd_credit_metadata(monkeypatch):
    _answers(monkeypatch, _Body(b'{"key_metadata": "n/a", "html": {"data": "x"}}'))
    client = contextdev.ContextDev("not-a-real-key")
    assert client._post({"url": "https://example.test/"})["html"] == {"data": "x"} and client.credits_used == 0
    _answers(monkeypatch, _Body(b'{"key_metadata": {"credits_consumed": "1"}}'))
    client._post({"url": "https://example.test/"})
    assert client.credits_used == 0


@pytest.mark.parametrize("error_body", [_Body(error=http.client.IncompleteRead(b"{")), _Body(b"[1]")])
def test_post_survives_a_bad_error_body(monkeypatch, error_body):
    def fail(*a, **k):
        raise urllib.error.HTTPError("https://example.test/", 404, "not found", {}, error_body)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    out = contextdev.ContextDev("not-a-real-key")._post({"url": "https://example.test/"}, patient=False)
    assert out["_http_error"] == 404


def test_cli_never_prints_a_traceback_for_a_bad_answer(tmp_path, monkeypatch, capsys):
    from swarm.collect import __main__ as cli
    _answers(monkeypatch, _Body(b"<html>maintenance</html>"))
    assert cli.main(["https://news.ycombinator.com/item?id=1", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "error:" in err


def test_cli_wraps_an_unexpected_failure_in_one_line(tmp_path, monkeypatch, capsys):
    from swarm.collect import __main__ as cli
    monkeypatch.setattr(cli, "collect", lambda *a, **k: (_ for _ in ()).throw(http.client.HTTPException("boom")))
    assert cli.main(["https://example.test/x", str(tmp_path / "o")]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_run_raises_collect_error_for_a_thread_without_comments(monkeypatch):
    from swarm.convert import ConvertError
    monkeypatch.setattr(collect_module, "analyse", lambda *a, **k: (_ for _ in ()).throw(ConvertError("no comments")))
    with pytest.raises(CollectError, match="no comments"):
        run(POST_LINK, history=5, client=FakeClient(bluesky_routes()))


def test_run_falls_back_to_no_similar_text_when_the_model_cannot_load(monkeypatch):
    from swarm import core
    from swarm.load import InputError
    real, calls = core.analyze, []

    def analyze(*args, similar_text=False, **kw):
        calls.append(similar_text)
        if similar_text:
            raise InputError("cannot load the similar-text model x: offline")
        return real(*args, **kw)
    monkeypatch.setattr(core, "analyze", analyze)
    result, _ = run(POST_LINK, history=5, client=FakeClient(bluesky_routes()))
    assert calls == [True, False]
    assert any("similar-text signal skipped" in w and "offline" in w for w in result["warnings"])


def test_other_input_errors_still_fail_the_run(monkeypatch):
    from swarm import core
    from swarm.load import InputError
    monkeypatch.setattr(core, "analyze", lambda *a, **k: (_ for _ in ()).throw(InputError("no usernames")))
    with pytest.raises(CollectError, match="no usernames"):
        run(POST_LINK, history=5, client=FakeClient(bluesky_routes()))


def test_history_and_participants_are_clamped():
    def route(url):
        return {"hits": []} if "search_by_date" in url else HN_ITEM
    bundle = collect(HN_LINK, history=500, max_participants=0, client=FakeClient(direct_routes=route))
    assert bundle["thread"]["history_per_commenter"] == 100 and bundle["thread"]["commenters_fetched"] == 1


# --- histories around the thread's date, most active first (handoff R2, R3) --------------------

def test_bluesky_history_pages_back_to_the_threads_date_and_keeps_the_posts_near_it():
    from swarm.collect.bluesky import _history
    from swarm.collect.around import when, window
    day = lambda d: f"2026-10-{d:02d}T12:00:00Z"
    pages = {None: {"feed": [{"post": bpost("x", "new", f"n{d}", created=day(d))} for d in (30, 29, 28)], "cursor": "c1"},
             "c1": {"feed": [{"post": bpost("x", "near", f"m{d}", created=day(d))} for d in (16, 15, 14, 3)], "cursor": "c2"}}
    client = FakeClient(direct_routes=lambda url: pages.get(parse_qs(urlparse(url).query).get("cursor", [None])[0], {"feed": []}))
    url, got = _history(client, {}, "did:plc:x", 2, window(when(day(15))))
    assert [f["post"]["record"]["createdAt"] for f in got["feed"]] == [day(15), day(16)]     # nearest first, at most 2
    assert len(client.calls) == 2 and "cursor" not in url                                   # stopped: day 3 is before the window
    _, none_near = _history(client, {}, "did:plc:x", 2, window(when("2025-01-01T00:00:00Z")))
    assert [f["post"]["record"]["text"] for f in none_near["feed"]] == ["new", "new"]       # nothing near: the newest


def test_hn_history_asks_for_the_threads_window_then_the_newest():
    seen = []

    def route(url):
        q = parse_qs(urlparse(url).query)
        if "search_by_date" not in url:
            return {**HN_ITEM, "created_at_i": 1_700_000_000}
        seen.append(q.get("numericFilters", [None])[0])
        if q.get("numericFilters") and "cy" in q["tags"][0]:
            return {"hits": []}
        return {"hits": [{"objectID": "9" + q["tags"][0], "author": "x", "comment_text": "w", "story_id": 1}]}
    bundle = collect(HN_LINK, history=5, client=FakeClient(direct_routes=route))
    assert f"created_at_i>={1_700_000_000 - 7 * 86400},created_at_i<={1_700_000_000 + 7 * 86400}" in seen
    assert seen.count(None) == 1 and bundle["thread"]["histories_ok"] == 4                 # cy had none near: newest


def test_the_most_active_commenters_get_a_history_first():
    client = FakeClient(direct_routes=hn_routes())
    bundle = collect(HN_LINK, history=5, max_participants=1, client=client)
    assert [c[1] for c in client.calls if "search_by_date" in c[1]][0].count("author_ann") == 1   # ann wrote 2 comments
    assert bundle["thread"]["commenters"] == 4 and bundle["thread"]["commenters_fetched"] == 1
    from swarm.collect.around import most_active
    assert most_active(["b", "a", "c", "a", "c", "d"]) == ["a", "c", "b", "d"]


def test_free_apis_default_to_500_participants_reddit_to_150():
    from swarm.collect import bluesky, hackernews, reddit
    assert bluesky.MAX_PARTICIPANTS == hackernews.MAX_PARTICIPANTS == 500
    assert getattr(reddit, "MAX_PARTICIPANTS", 150) == 150
