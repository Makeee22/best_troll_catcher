"""Site-specific readers: Context.dev parser output (from_parsed) and saved pages (from_html).

Standard library only; the HTML is untrusted and is parsed, never executed.
The Reddit page reader is a port of frontend/api/reddit_html.py (Reddit's shreddit-* elements).
"""
import re
from html.parser import HTMLParser

MAX_COMMENTS = 5000
VOID_TAGS = {"br", "hr", "img", "wbr"}  # no end tag, so they must not count as open


def _utc(value):
    """'2026-06-07T04:24:13.731000+0000' -> '2026-06-07T04:24:13Z'."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", value or "")
    return m.group(1) + "Z" if m else ""


def _id(thing):
    """'t1_oq7lyly' -> 'oq7lyly'."""
    return re.sub(r"^t\d_", "", str(thing or ""))


class _RedditParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.post = None
        self.comments = {}      # thingid -> row, in document order
        self.text_for = None    # thingid whose text is being read
        self.open = []          # open tags inside that text element, outermost first
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.text_for is not None and tag in ("shreddit-comment", "shreddit-post"):
            self._finish()  # an unclosed tag in the text must not swallow the rest of the page
        if self.text_for is not None:
            if tag in VOID_TAGS:
                if tag == "br":
                    self.parts.append("\n")
                return
            self.open.append(tag)
            if tag in ("p", "li"):
                self.parts.append("\n")
            return
        if tag == "shreddit-post" and self.post is None:
            count = a.get("comment-count") or ""
            self.post = {"thing": a.get("id") or "", "author": a.get("author") or "",
                         "created": _utc(a.get("created-timestamp")), "text": "",
                         "expected": int(count) if count.isdigit() else None}
        elif tag == "shreddit-comment" and len(self.comments) < MAX_COMMENTS:
            thing = a.get("thingid") or ""
            if thing and thing not in self.comments:
                self.comments[thing] = {"comment_id": _id(thing), "username": a.get("author") or "", "display_name": "",
                                        "text": "", "timestamp": _utc(a.get("created")), "parent_id": _id(a.get("parentid")),
                                        "thread_id": _id(a.get("postid")), "source": "thread"}
        elif (a.get("id") or "").endswith(("-comment-rtjson-content", "-post-rtjson-content")):
            thing = a["id"].rsplit("-", 3)[0]
            if thing in self.comments or (self.post and thing == self.post["thing"]):
                self.text_for, self.open, self.parts = thing, [tag], []

    def handle_endtag(self, tag):
        if self.text_for is None or tag in VOID_TAGS:
            return
        if tag in self.open:  # an end tag with no open match is ignored; unclosed tags inside it are closed with it
            del self.open[len(self.open) - 1 - self.open[::-1].index(tag):]
            if not self.open:
                self._finish()

    def _finish(self):
        text = re.sub(r"[ \t]+", " ", "".join(self.parts))
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if self.text_for in self.comments:
            self.comments[self.text_for]["text"] = text
        else:
            self.post["text"] = text
        self.text_for = None

    def close(self):
        super().close()
        if self.text_for is not None:  # a truncated page
            self._finish()

    def handle_data(self, data):
        if self.text_for is not None and "blockquote" not in self.open:
            self.parts.append(data)


def from_html(html, page_url):
    """Rows of a saved Reddit thread page; ([], [], []) for any other HTML."""
    if "<shreddit-" not in html:
        return [], [], []
    p = _RedditParser()
    p.feed(html)
    p.close()
    rows = list(p.comments.values())
    warnings = []
    if p.post:
        post_id = _id(p.post["thing"])
        for r in rows:
            r["thread_id"] = r["thread_id"] or post_id
        if p.post["text"] and post_id:
            rows.insert(0, {"comment_id": post_id, "username": p.post["author"], "display_name": "",
                            "text": p.post["text"], "timestamp": p.post["created"], "parent_id": "",
                            "thread_id": post_id, "source": "thread"})
        if p.post["expected"] and p.post["expected"] > len(p.comments):
            warnings.append(f"converter: read {len(p.comments)} of {p.post['expected']} comments on the Reddit thread "
                            "(the rest were not loaded on the page, e.g. behind Reddit's \"load more\")")
    return rows, [], warnings


def _reddit_user(data, page_url):
    user = _d(data.get("user"))
    name = _s(user.get("username"))
    comments = [c for c in data.get("comments") if isinstance(c, dict)] if isinstance(data.get("comments"), list) else []
    rows = [{"comment_id": _s(c.get("id")), "username": name, "display_name": "", "text": _s(c.get("body")),
             "timestamp": _s(c.get("posted_at")), "parent_id": _s(c.get("parent_id")),
             "thread_id": _id(_d(c.get("post")).get("id")), "source": "history"}
            for c in comments]
    return rows, [{"username": name, "display_name": "", "created_at": _s(user.get("created_at")), "post_count": ""}], []


def _d(x):
    return x if isinstance(x, dict) else {}


def _s(x):
    """A text value; anything that is not a string or number (null, list, dict) is empty."""
    return str(x) if isinstance(x, (str, int, float)) and not isinstance(x, bool) else ""


def _review_rows(items, thread_id, fields, count=lambda item: ""):
    """Rows (and profiles with a post count) for a list of reviews; fields(item) -> (username, display_name, text, timestamp)."""
    rows, profiles = [], []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        username, display_name, text, timestamp = fields(item)
        rows.append({"comment_id": _s(item.get("id")), "username": username, "display_name": display_name, "text": text,
                     "timestamp": timestamp, "parent_id": "", "thread_id": thread_id, "source": "thread"})
        if username and text and count(item):  # merge drops placeholder authors from the profiles too
            profiles.append({"username": username, "display_name": display_name, "created_at": "", "post_count": count(item)})
    return rows, profiles, []


def _join(*parts):
    """Text parts joined by newlines; a list part contributes its string items."""
    flat = [q for p in parts for q in (p if isinstance(p, list) else [p])]
    return "\n".join(p for p in map(_s, flat) if p)


def _names_only(kind, mapper):
    note = f"converter: {kind} gives display names only: two people with the same name count as one account"
    return lambda data, page_url: (*mapper(data, page_url)[:2], [note])


def _google_maps(data, page_url):
    def who(r):
        u = _d(r.get("user"))
        m = re.search(r"contrib/(\d+)", _s(u.get("link")))
        return m.group(1) if m else _s(u.get("name")), _s(u.get("name")), _s(r.get("snippet")), _s(r.get("isoDate"))
    return _review_rows(data.get("reviews"), _s(data.get("featureId")) or _s(data.get("cid")), who,
                        lambda r: _s(_d(r.get("user")).get("reviews")))


def _app_store(data, page_url):
    author = lambda r: (_s(r.get("author")), _s(r.get("author")), _join(r.get("title"), r.get("text")), _s(r.get("created_at")))
    return _review_rows(data.get("reviews"), _s(data.get("app_id")), author)


def _google_play(data, page_url):
    author = lambda r: (_s(r.get("author")), _s(r.get("author")), _s(r.get("text")), _s(r.get("created_at")))
    return _review_rows(data.get("reviews"), _s(data.get("app_id")), author)


def _tripadvisor(data, page_url):
    def who(r):
        a = _d(r.get("author"))
        return _s(a.get("username")) or _s(a.get("id")), _s(a.get("name")), _join(r.get("title"), r.get("text")), _s(r.get("published_at"))
    return _review_rows(data.get("reviews"), _s(_d(data.get("location")).get("id")), who,
                        lambda r: _s(_d(r.get("author")).get("contribution_count")))


def _yelp(data, page_url):
    def who(r):
        a = _d(r.get("author"))
        return _s(a.get("id")), _s(a.get("name")), _s(r.get("text")), _s(r.get("updated_at"))
    return _review_rows(data.get("reviews"), _s(_d(data.get("business")).get("id")), who,
                        lambda r: _s(_d(r.get("author")).get("review_count")))


def _g2(data, page_url):
    def who(r):
        name = _s(_d(r.get("reviewer")).get("name"))
        return name, name, _join(r.get("likes"), r.get("dislikes"), r.get("problems_solved")), _s(r.get("published_at"))
    return _review_rows(data.get("reviews"), _s(_d(data.get("product")).get("slug")), who)


def _tiktok(data, page_url):
    def who(c):
        a = _d(c.get("author"))
        return _s(a.get("username")), _s(a.get("nickname")), _s(c.get("text")), _s(c.get("posted_at"))
    video = re.search(r"/video/(\d+)", page_url or "")
    return _review_rows(data.get("comments"), video.group(1) if video else "", who)


MAPPERS = {"reddit-user": _reddit_user, "google-maps-reviews": _google_maps,
           "app-store-reviews": _names_only("app-store-reviews", _app_store),
           "google-play-reviews": _names_only("google-play-reviews", _google_play),
           "tripadvisor-reviews": _tripadvisor, "yelp-reviews": _yelp,
           "g2-reviews": _names_only("g2-reviews", _g2), "tiktok-comments": _tiktok}


def from_parsed(parsed, page_url):
    """Rows from Context.dev's parser output; ({type, success, data}) -> (rows, profiles, warnings)."""
    parsed = _d(parsed)
    kind = parsed.get("type") if isinstance(parsed.get("type"), str) else ""
    if kind not in MAPPERS:
        return [], [], [f"converter: no mapper for parser {kind}"]
    if not parsed.get("success"):
        return [], [], [f"converter: Context.dev parser {kind} failed: {parsed.get('error_code') or parsed.get('error') or 'unknown'}"]
    return MAPPERS[kind](_d(parsed.get("data")), page_url)


# --- public JSON APIs: Bluesky (AT Protocol) and Hacker News (Algolia) ---

BSKY_VISIBLE = "app.bsky.feed.defs#threadViewPost"


def _row(cid, username, text, source, display_name="", timestamp="", parent_id="", thread_id="", links="", repost_of=""):
    return {"comment_id": cid, "username": username, "display_name": display_name, "text": text, "timestamp": timestamp,
            "parent_id": parent_id, "thread_id": thread_id, "source": source, "links": links, "repost_of": repost_of}


def _profile(username, display_name="", created_at="", post_count="", bio=""):
    return {"username": username, "display_name": display_name, "created_at": created_at, "post_count": post_count, "bio": bio}


def _name(actor):
    """The account name: the handle, or the DID when the handle is missing or 'handle.invalid' (else every broken handle is one user)."""
    handle = _s(actor.get("handle"))
    return handle if handle and handle != "handle.invalid" else _s(actor.get("did")) or handle


def _bsky_post(post, source):
    """(row, profile) of a Bluesky post view; the row's thread is its root, or itself for a root post."""
    author, record = _d(post.get("author")), _d(post.get("record"))
    reply = _d(record.get("reply"))
    uri = _s(post.get("uri"))
    features = [f for facet in _list(record.get("facets")) for f in _list(_d(facet).get("features"))]
    links = [_s(_d(f).get("uri")) for f in features if _s(_d(f).get("$type")).endswith("#link")]
    links.append(_s(_d(_d(post.get("embed")).get("external")).get("uri")))
    handle = _name(author)
    row = _row(uri, handle, _s(record.get("text")), source, _s(author.get("displayName")), _s(record.get("createdAt")),
               _s(_d(reply.get("parent")).get("uri")), _s(_d(reply.get("root")).get("uri")) or uri, " ".join(dict.fromkeys(filter(None, links))))  # a link in the text and the card counts once
    return row, _profile(handle, row["display_name"], _s(author.get("createdAt")))  # the profile only matters with a creation date


def _list(x):
    return x if isinstance(x, list) else []


def _bsky_thread(thread):
    rows, profiles, hidden, stack = [], [], 0, [thread]
    root = _d(thread.get("post"))
    while stack and len(rows) < MAX_COMMENTS:
        n = stack.pop()
        if not isinstance(n, dict) or n.get("$type", BSKY_VISIBLE) != BSKY_VISIBLE:  # blocked, deleted and not-found nodes carry another type
            hidden += 1
            continue
        row, profile = _bsky_post(_d(n.get("post")), "thread")
        rows.append(row)
        profiles += [profile] if profile["created_at"] else []
        stack.extend(reversed(_list(n.get("replies"))))
    warnings = []
    if hidden:
        warnings.append(f"converter: left out {hidden} Bluesky post{'' if hidden == 1 else 's'} not visible (blocked, deleted or not found)")
    total, got = root.get("replyCount"), len(rows) - 1
    if isinstance(total, int) and total > got:
        warnings.append(f"converter: read {max(got, 0)} of {total} replies on the Bluesky thread")
    return rows, profiles, warnings


def _bsky_feed(feed):
    rows, profiles = [], []
    for item in _list(feed):
        item = _d(item)
        reason, post = _d(item.get("reason")), _d(item.get("post"))
        if _s(reason.get("$type")).endswith("#reasonRepost"):
            by = _d(reason.get("by"))
            handle = _name(by)
            if handle == _name(_d(post.get("author"))):  # a repost of one's own post says nothing new
                continue
            rows.append(_row(f"repost:{handle}:{_s(post.get('uri'))}", handle, "", "history", timestamp=_s(reason.get("indexedAt")),
                             repost_of=_s(post.get("uri"))))
            profiles += [_profile(handle, _s(by.get("displayName")), _s(by.get("createdAt")))] if by.get("createdAt") else []
        elif post:
            row, profile = _bsky_post(post, "history")
            rows.append(row)
            profiles += [profile] if profile["created_at"] else []
    return rows, profiles, []


def _bsky_profiles(items):
    return [], [_profile(_name(p), _s(p.get("displayName")), _s(p.get("createdAt")), _s(p.get("postsCount")), _s(p.get("description")))
              for p in map(_d, _list(items))], []


class _PlainText(HTMLParser):
    """Algolia's HTML (<p>, <a href>, <i>, <pre><code>) as plain text plus the link URLs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.anchor = [], [], None  # anchor: [href, text parts] while inside <a href>

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "pre"):
            self.handle_data("\n")
        href = dict(attrs).get("href") if tag == "a" else None
        if href:
            self._end_anchor()
            self.links.append(href)
            self.anchor = [href, []]

    def handle_endtag(self, tag):
        if tag == "a":
            self._end_anchor()

    def _end_anchor(self):
        if self.anchor:
            href, text = self.anchor[0], "".join(self.anchor[1])
            # Algolia cuts a long URL's anchor text with "..."; the href is the whole URL. Any other label stays as written.
            label = text.strip()
            cut = label.rstrip("….").rstrip() if label.endswith(("...", "…")) else None
            keep = cut and href.startswith(cut) and cut.startswith("http")
            self.parts.append(text[:len(text) - len(text.lstrip())] + href + text[len(text.rstrip()):] if keep else text)
            self.anchor = None

    def handle_data(self, data):
        (self.anchor[1] if self.anchor else self.parts).append(data)

    def close(self):
        super().close()
        self._end_anchor()


def _html_text(value):
    """(text, links) of an Algolia HTML string."""
    p = _PlainText()
    p.feed(_s(value))
    p.close()
    text = re.sub(r"[ \t]+", " ", "".join(p.parts))
    return re.sub(r"\s*\n\s*", "\n", text).strip(), " ".join(p.links)


def _hn_row(item, source, story_id=""):
    text, links = _html_text(item.get("text") if "text" in item else item.get("comment_text"))
    return _row(_s(item.get("id") if "id" in item else item.get("objectID")), _s(item.get("author")), text, source,
                timestamp=_s(item.get("created_at")), parent_id=_s(item.get("parent_id")),
                thread_id=_s(item.get("story_id")) or story_id, links=links)


def _hn_item(item):
    rows, stack = [], [item]
    story = _s(item.get("id"))
    while stack and len(rows) < MAX_COMMENTS:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        row = _hn_row(n, "thread", story)
        if n is item:  # the story: a row only with its own text or link (Ask HN, link posts)
            row["links"] = " ".join(filter(None, [row["links"], _s(n.get("url"))]))
            if not (row["text"] or row["links"]):
                row = None
        if row:
            rows.append(row)
        stack.extend(reversed(_list(n.get("children"))))
    return rows, [], []


def from_json(data, page_url):
    """Rows of a public API response: Bluesky thread, author feed and profiles, Hacker News item and search hits."""
    data = _d(data)
    if "thread" in data:
        return _bsky_thread(_d(data["thread"]))
    if "feed" in data:
        return _bsky_feed(data["feed"])
    if "profiles" in data:
        return _bsky_profiles(data["profiles"])
    if "id" in data and isinstance(data.get("children"), list):
        return _hn_item(data)
    if "hits" in data:
        return [_hn_row(h, "history") for h in _list(data["hits"]) if isinstance(h, dict)], [], []
    return [], [], [f"converter: unrecognised JSON on {page_url}"]
