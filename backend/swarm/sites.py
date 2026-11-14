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
        self.depth = 0          # open tags inside that text element
        self.quote = 0          # open <blockquote>s inside it: the quoted parent is not this author's text
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.text_for is not None:
            if tag in VOID_TAGS:
                if tag == "br":
                    self.parts.append("\n")
                return
            self.depth += 1
            self.quote += tag == "blockquote"
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
                self.text_for, self.depth, self.quote, self.parts = thing, 1, 0, []

    def handle_endtag(self, tag):
        if self.text_for is None or tag in VOID_TAGS:
            return
        self.depth -= 1
        if tag == "blockquote" and self.quote:
            self.quote -= 1
        if self.depth <= 0:
            text = re.sub(r"[ \t]+", " ", "".join(self.parts))
            text = re.sub(r"\s*\n\s*", "\n", text).strip()
            if self.text_for in self.comments:
                self.comments[self.text_for]["text"] = text
            else:
                self.post["text"] = text
            self.text_for = None

    def handle_data(self, data):
        if self.text_for is not None and not self.quote:
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


def _reddit_user(data):
    user = data.get("user") or {}
    name = user.get("username") or ""
    rows = [{"comment_id": c.get("id") or "", "username": name, "display_name": "", "text": c.get("body") or "",
             "timestamp": c.get("posted_at") or "", "parent_id": c.get("parent_id") or "",
             "thread_id": _id((c.get("post") or {}).get("id")), "source": "history"}
            for c in data.get("comments") or []]
    return rows, [{"username": name, "display_name": "", "created_at": user.get("created_at") or "", "post_count": ""}], []


MAPPERS = {"reddit-user": _reddit_user}


def from_parsed(parsed, page_url):
    """Rows from Context.dev's parser output; ({type, success, data}) -> (rows, profiles, warnings)."""
    kind = parsed.get("type") or ""
    if kind not in MAPPERS:
        return [], [], [f"converter: no mapper for parser {kind}"]
    if not parsed.get("success"):
        return [], [], [f"converter: Context.dev parser {kind} failed: {parsed.get('error_code') or parsed.get('error') or 'unknown'}"]
    return MAPPERS[kind](parsed.get("data") or {})
