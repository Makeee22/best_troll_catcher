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
                            "(the rest were not loaded on the saved page)")
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
