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


def test_bluesky_bundle_keeps_responses_unchanged_as_json_pages():
    progress = []
    client = FakeClient(bluesky_routes())
    bundle = collect(POST_LINK, history=5, on_progress=lambda d, t: progress.append((d, t)), client=client)
    assert bundle["site"] == "bluesky" and bundle["url"] == POST_LINK and bundle["collected_at"].endswith("Z")
    pages = bundle["pages"]
    assert pages[0]["role"] == "thread" and pages[0]["json"] == THREAD
    feeds = [p for p in pages if "feed" in p.get("json", {})]
    profile_pages = [p for p in pages if "profiles" in p.get("json", {})]
    assert len(feeds) == 4 and all(p["role"] == "profile" for p in feeds + profile_pages)
    assert [len(p["json"]["profiles"]) for p in profile_pages] == [4]
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert all("limit=5" in c[1] for c in client.calls if "getAuthorFeed" in c[1])
    t = bundle["thread"]
    assert (t["platform"], t["post_id"], t["commenters"], t["commenters_fetched"], t["history_per_commenter"]) == \
        ("Bluesky", ROOT["uri"], 4, 4, 5)
    assert (t["histories_ok"], t["histories_failed"]) == (4, 0)
    cov = bundle["coverage"]
    assert cov["comments_found"] == 3 and cov["comments_expected"] == 4     # sum of replyCount: 3 + 1
    assert any("1 could not be" in n or "deleted, hidden or blocked" in n for n in cov["notes"])
    assert bundle["credits_used"] == len(client.calls)


def test_bluesky_participant_cap_and_failed_histories_are_noted_and_skipped():
    client = FakeClient(bluesky_routes(fail={"did:plc:bob"}))
    bundle = collect(POST_LINK, history=5, max_participants=3, client=client)
    t = bundle["thread"]
    assert (t["commenters"], t["commenters_fetched"], t["histories_ok"], t["histories_failed"]) == (4, 3, 2, 1)
    assert sum(1 for p in bundle["pages"] if "feed" in p.get("json", {})) == 2
    notes = " ".join(bundle["coverage"]["notes"])
    assert "first 3" in notes and "1 participants could not be fetched" in notes


def test_bluesky_post_not_found():
    def route(url):
        if "resolveHandle" in url:
            return {"did": "did:plc:rootuser"}
        return {"thread": {"$type": "app.bsky.feed.defs#notFoundPost"}}
    with pytest.raises(CollectError, match="not found, or it is not public"):
        collect(POST_LINK, client=FakeClient(route))


def test_bluesky_bundle_converts_and_broken_handles_become_the_did():
    bundle = collect(POST_LINK, history=5, client=FakeClient(bluesky_routes()))
    comments, profiles, _ = convert(bundle)
    names = {c["username"] for c in comments}
    assert "did:plc:carol" in names and "alice.example.test" in names
    assert any(c["repost_of"] for c in comments)
    assert {p["created_at"] for p in profiles} == {"2024-01-01T00:00:00Z"}


def test_run_gives_the_result_a_readable_label_and_puts_coverage_first():
    result, bundle = run(POST_LINK, similar_text=False, history=5, client=FakeClient(bluesky_routes()))
    assert result["source"]["comments_file"] == f"Bluesky thread {ROOT['uri']}"
    assert result["source"]["accounts"] == 4
    assert any("deleted, hidden or blocked" in w for w in result["warnings"][:3])
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
        if u.path.startswith("/api/v1/search"):
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
