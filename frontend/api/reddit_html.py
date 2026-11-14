"""Read a Reddit thread from a page the user saved in their own browser (Ctrl+S).

Reddit's current site renders each comment as a <shreddit-comment> element whose attributes
carry the author, time, id and parent id; the text is in the element with
id="<thingid>-comment-rtjson-content". The post itself is a <shreddit-post> element.
Only what the user's browser had loaded is in the file: "load more" replies are not.

    thread = parse_thread(html_bytes)
    thread["post"], thread["comments"], thread["authors"]

Standard library only. The HTML is untrusted: it is parsed, never executed or served.
"""
import re
from html.parser import HTMLParser

MAX_COMMENTS = 5000


def _utc(value):
    """'2026-06-07T04:24:13.731000+0000' -> '2026-06-07T04:24:13Z'."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", value or "")
    return m.group(1) + "Z" if m else ""


def _id(thing):
    """'t1_oq7lyly' -> 'oq7lyly'; Reddit's own ids without the type prefix."""
    return re.sub(r"^t\d_", "", thing or "")


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.post = None
        self.comments = {}          # thingid -> comment dict, in document order
        self.text_for = None        # thingid whose text is being read
        self.depth = 0              # open tags inside that text element
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.text_for is not None:
            self.depth += 1
            if tag in ("p", "br", "li"):
                self.parts.append("\n")
            return
        if tag == "shreddit-post" and self.post is None:
            self.post = {
                "id": _id(a.get("id")),
                "author": a.get("author") or "",
                "title": a.get("post-title") or "",
                "subreddit": a.get("subreddit-prefixed-name") or "",
                "created": _utc(a.get("created-timestamp")),
                "comment_count": int(a["comment-count"]) if (a.get("comment-count") or "").isdigit() else None,
            }
        elif tag == "shreddit-comment" and len(self.comments) < MAX_COMMENTS:
            thing = a.get("thingid") or ""
            if thing and thing not in self.comments:
                self.comments[thing] = {
                    "comment_id": _id(thing),
                    "username": a.get("author") or "",
                    "timestamp": _utc(a.get("created")),
                    "parent_id": _id(a.get("parentid")),
                    "thread_id": _id(a.get("postid")),
                    "depth": int(a["depth"]) if (a.get("depth") or "").isdigit() else None,
                    "text": "",
                }
        elif (a.get("id") or "").endswith("-comment-rtjson-content"):
            thing = a["id"][: -len("-comment-rtjson-content")]
            if thing in self.comments:
                self.text_for, self.depth, self.parts = thing, 1, []

    def handle_endtag(self, tag):
        if self.text_for is None:
            return
        self.depth -= 1
        if self.depth <= 0:
            text = re.sub(r"[ \t]+", " ", "".join(self.parts))
            self.comments[self.text_for]["text"] = re.sub(r"\s*\n\s*", "\n", text).strip()
            self.text_for = None

    def handle_data(self, data):
        if self.text_for is not None:
            self.parts.append(data)


class NotARedditThread(ValueError):
    pass


def parse_thread(raw):
    """Saved page bytes -> {"post", "comments", "authors", "found", "expected"}."""
    html = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    p = _Parser()
    p.feed(html)
    p.close()
    if p.post is None and not p.comments:
        raise NotARedditThread("This does not look like a saved Reddit thread (no post or comments found). "
                               "Open the thread on reddit.com, scroll to load the comments, then save the page.")
    comments = [c for c in p.comments.values() if c["username"] and c["username"] != "[deleted]"]
    authors = []
    for name in [p.post["author"] if p.post else ""] + [c["username"] for c in comments]:
        if name and name != "[deleted]" and name not in authors:
            authors.append(name)
    return {
        "post": p.post,
        "comments": comments,
        "authors": authors,
        "found": len(p.comments),
        "expected": p.post["comment_count"] if p.post else None,
    }
