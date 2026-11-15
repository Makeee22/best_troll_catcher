"""Any other link: Context.dev renders the page and the comments come from its schema.org markup (Comment, Answer,
Review, DiscussionForumPosting), which most forum software and many news and Q&A sites publish: XenForo, Invision,
Discourse, phpBB with an extension, WordPress themes. One page, no commenter histories; swarm.convert reads the html
(schemaorg.from_html), so this module only fetches it and checks that there is something to read.
"""
from urllib.parse import urlparse

from .. import schemaorg
from .contextdev import CollectError


def matches(url):
    return True    # the last resort, after every site module


def collect(url, client, history, max_participants, on_progress):
    host = (urlparse(url).hostname or url).removeprefix("www.")
    try:
        html = client.fetch_html(url)
    except CollectError as e:     # no key, no credits, or the page would not load
        raise CollectError(f"This site is not supported yet: {host} (reading its page failed: {e})") from None
    rows = schemaorg.from_html(html, url) if html else []
    if not rows:
        raise CollectError(f"This site is not supported yet: {host} (the page has no standard comment markup to read). "
                           "Save the page in the browser and upload it, or export the comments as a CSV.")
    authors = {r["username"] for r in rows if r["username"]}
    return {
        "pages": [{"url": url, "role": "thread", "html": html}],
        "notes": [f"thread: read from the page's schema.org markup; one page only (later pages of a long thread are not "
                  f"fetched), and no commenter's other posts"],
        "found": len(rows), "expected": None,
        "thread": {"platform": host, "label": f"{host} page", "url": url, "commenters": len(authors),
                   "commenters_fetched": 0, "history_per_commenter": 0, "histories_ok": 0, "histories_failed": 0},
    }
