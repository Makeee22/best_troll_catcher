"""schema.org Comment / Review / Answer reader: JSON-LD blocks and microdata on a saved page.

Standard library only; the HTML and JSON are untrusted and are parsed, never executed.
Both markups are turned into one tree of dicts (JSON-LD as written, microdata as nested items),
and one iterative walk finds the comments in it.
"""
import hashlib
import json
import re
from collections import Counter
from html.parser import HTMLParser

from .sites import MAX_COMMENTS

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
VALUE_ATTR = {"a": "href", "area": "href", "link": "href", "meta": "content", "time": "datetime", "data": "value",
              "meter": "value", "img": "src", "source": "src", "audio": "src", "video": "src", "iframe": "src", "embed": "src"}
TEXT_FIELDS = ("text", "reviewBody", "articleBody", "description")
MAX_TEXT_PROPS = 32  # nested text-collecting elements; deeper ones are not collected (every text chunk goes to each open one)
POSTS = {"DiscussionForumPosting", "Question"}  # the opening post: a row too when it has text, but not the parent of the comments


def _s(x):
    """A text value; anything that is not a string or number (null, list, dict) is empty."""
    return str(x) if isinstance(x, (str, int, float)) and not isinstance(x, bool) else ""


def _first(x):
    return x[0] if isinstance(x, list) and x else x


def _add(d, key, value):
    """d[key] = value; a repeated key becomes a list (as JSON-LD writes several values)."""
    if key not in d:
        d[key] = value
    elif isinstance(d[key], list):
        d[key].append(value)
    else:
        d[key] = [d[key], value]


def _clean(parts):
    text = re.sub(r"[ \t]+", " ", "".join(parts))
    return re.sub(r"\s*\n\s*", "\n", text).strip()


class _Page(HTMLParser):
    """Collects the JSON-LD script blocks and builds the microdata items as nested dicts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []     # JSON-LD source texts
        self.roots = []      # top-level microdata items, in document order
        self.stack = []      # open elements: [tag, owner scope, prop names, value from an attribute, text parts or None]
        self.bufs = []       # the stack frames that collect text
        self.open = Counter()  # open elements per tag name: a stray end tag is rejected without scanning the stack
        self.scopes = []     # open item scopes, innermost last: (stack depth, item dict)
        self.script = None   # the open script or style tag: [tag, parts or None (not JSON-LD)]

    def handle_starttag(self, tag, attrs):
        if self.script:
            return
        a = {k: v or "" for k, v in attrs}
        if tag in ("script", "style"):
            self.script = [tag, [] if tag == "script" and a.get("type", "").strip().lower().startswith("application/ld+json") else None]
            return
        if tag in ("p", "li", "br"):
            for f in self.bufs:
                f[4].append("\n")
        props = a.get("itemprop", "").split()
        owner = self.scopes[-1][1] if self.scopes else None
        if "itemscope" in a:
            item = {"@type": a.get("itemtype", "").split(), "@id": a.get("itemid", "")}
            if owner is None:
                self.roots.append(item)
            for name in props or ["@nested"]:
                if owner is not None:
                    _add(owner, name, item)
            if tag not in VOID:
                self.scopes.append((len(self.stack), item))
        if tag in VOID:
            if props and "itemscope" not in a and owner is not None:
                for name in props:
                    _add(owner, name, a.get(VALUE_ATTR.get(tag, ""), ""))
            return
        collects = bool(props) and "itemscope" not in a and len(self.bufs) < MAX_TEXT_PROPS
        frame = [tag, owner, props if collects else [], a.get(VALUE_ATTR.get(tag, ""), None) if collects else None,
                 [] if collects else None]
        self.stack.append(frame)
        self.open[tag] += 1
        if collects:
            self.bufs.append(frame)

    def handle_endtag(self, tag):
        if self.script:
            if tag == self.script[0]:
                if self.script[1] is not None:
                    self.blocks.append("".join(self.script[1]))
                self.script = None
            return
        if not self.open[tag]:  # an end tag with no open match is ignored
            return
        for i in range(len(self.stack) - 1, -1, -1):  # unclosed tags inside the match close with it
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    self._close()
                return

    def _close(self):
        frame = self.stack.pop()
        self.open[frame[0]] -= 1
        while self.scopes and self.scopes[-1][0] >= len(self.stack):
            self.scopes.pop()
        if frame[4] is not None:
            self.bufs.pop()
            value = frame[3] if frame[3] is not None else _clean(frame[4])
            if frame[1] is not None:
                for name in frame[2]:
                    _add(frame[1], name, value)

    def handle_data(self, data):
        if self.script:
            if self.script[1] is not None:
                self.script[1].append(data)
        else:
            for f in self.bufs:
                f[4].append(data)

    def close(self):
        super().close()
        while self.stack:  # a truncated page
            self._close()
        if self.script and self.script[1] is not None:
            self.blocks.append("".join(self.script[1]))


def _types(node):
    """Type names of a node: '@type' as a string or list, with any 'https://schema.org/' prefix cut off."""
    kinds = node.get("@type")
    return [_s(k).rsplit("/", 1)[-1].rsplit("#", 1)[-1] for k in (kinds if isinstance(kinds, list) else [kinds])]


def _is_comment(kinds):
    return any(t in ("Comment", "Answer") or t.endswith("Review") for t in kinds)


def _found(roots):
    """(node, index of the enclosing comment or -1, thread id) of every comment, in document order; iterative, so depth is free."""
    out, stack = [], [(r, -1, "") for r in reversed(roots)]
    while stack:
        node, parent, thread = stack.pop()
        if isinstance(node, list):
            stack.extend((n, parent, thread) for n in reversed(node))
        elif isinstance(node, dict):
            kinds = _types(node)
            boiler = bool({"Answer", "Question"}.intersection(kinds)) and not _has_author(node)  # FAQPage answers are the site's own text
            comment = _is_comment(kinds) and not boiler
            if node.get("@type") and not comment:  # the enclosing post, article or product names the thread
                thread = _s(node.get("@id")) or _s(node.get("url")) or thread
            if comment or (not boiler and POSTS.intersection(kinds) and _field(node, TEXT_FIELDS[:3])):
                if len(out) >= MAX_COMMENTS:
                    break
                out.append((node, parent, thread))
                if comment:
                    parent = len(out) - 1
            stack.extend((v, parent, thread) for v in reversed(list(node.values())) if isinstance(v, (dict, list)))
    return out


def _field(node, keys):
    return next((v for v in (_s(_first(node.get(k))) for k in keys) if v), "")


def _has_author(node):
    """A named author who is not an Organization."""
    a = _first(node.get("author"))
    if isinstance(a, dict):
        return "Organization" not in _types(a) and bool(_field(a, ("url", "identifier", "name")))
    return bool(_s(a))


def _author(node):
    a = _first(node.get("author"))
    if isinstance(a, dict):
        return _field(a, ("url", "identifier", "name")), _s(_first(a.get("name")))
    return _s(a), _s(a)


def _rows(found, page_url, salt):
    rows, ids, first = [], [], {}
    for i, (node, parent, thread) in enumerate(found):
        cid = _field(node, ("@id", "url", "identifier"))
        username, display_name = _author(node)
        text = _field(node, TEXT_FIELDS)
        if cid in first:
            if first[cid] == (username, text):  # the same comment reached twice (nested and in @graph, or a repeated block)
                ids.append(cid)
                continue
            cid = ""  # reviews that all carry the page's url must stay apart
        if not cid:
            cid = f"sx{salt}-{i}"  # the salt keeps ids of different pages (and frames) apart, so merge does not drop them
        first[cid] = (username, text)
        ids.append(cid)
        rows.append({"comment_id": cid, "username": username, "display_name": display_name, "text": text,
                     "timestamp": _field(node, ("dateCreated", "datePublished")), "parent_id": ids[parent] if parent >= 0 else "",
                     "thread_id": thread or page_url, "source": "thread", "links": "", "repost_of": ""})
    return rows


def from_html(html, page_url):
    """Comment rows from the JSON-LD and microdata of a saved page; [] when it has none."""
    if not isinstance(html, str) or not re.search(r"ld\+json|itemscope", html, re.I):
        return []
    page = _Page()
    page.feed(html)
    page.close()
    roots = []
    for block in dict.fromkeys(page.blocks):  # a block repeated verbatim is the same markup
        try:
            roots.append(json.loads(block))
        except (ValueError, RecursionError):  # one bad block must not hide the others
            continue
    # a page that carries both markups (Discourse does) describes the same posts twice: the fuller one wins, JSON-LD on a tie
    # (XenForo's JSON-LD holds only the opening post, its microdata every reply)
    salt = hashlib.blake2s(f"{page_url}\0{html}".encode("utf-8", "replace"), digest_size=4).hexdigest()
    ld, micro = _found(roots), _found(page.roots)
    return _rows(micro if len(micro) > len(ld) else ld, page_url, salt)
