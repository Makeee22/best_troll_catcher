"""News check for one cluster: was what the group shared also in the news at the time? (Context.dev news search)

One of the innocent look-alikes the team designs for is breaking news: many ordinary people share the same link or
headline at once. Before a language model explains a cluster, we look up news coverage of the group's most shared
items in the window when the group was active, and hand the hits to the model as evidence (N1, N2, ...) and to the
page. Search results are candidates: the model and the reader judge whether they are really about the same thing.

    news = check(cluster)   # [{"item": "E1", "query": ..., "articles": [{title, url, source, published_at}]}], never raises

Context.dev: POST https://api.context.dev/v1/news/search, natural-language query, 1 credit per 10 results.
Needs CONTEXT_DEV_API_KEY. Only public post texts and links are sent, with @handles removed.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.context.dev/v1/news/search"
ITEMS = 3            # most shared items checked per cluster
PER_ITEM = 5         # articles per item
MARGIN = timedelta(days=2)


def _when(iso):
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _query(item):
    value = item.get("value") or ""
    if item.get("kind") == "link":
        m = re.match(r"https?://(?:www\.)?([^/?#]+)([^?#]*)", value)
        if not m:
            return None
        words = re.findall(r"[A-Za-z0-9]{3,}", m.group(2))
        return (m.group(1) + " " + " ".join(words[:12])).strip()[:300]
    if item.get("kind") in ("text", "similar_text"):
        text = re.sub(r"https?://\S+|(?<![\w/])@[\w.\-]+|(?<![\w/])u/[\w-]+", " ", value)
        words = re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text)
        return " ".join(words[:25]) if len(words) >= 5 else None
    return None


def _search(key, query, start, end):
    body = {"searchBy": {"type": "natural_language", "query": query}, "limit": PER_ITEM}
    if start and end:
        body["filterBy"] = {"date": {"from": int(start.timestamp() * 1000), "to": int(end.timestamp() * 1000)}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        out = json.load(r)
    return [{"title": a.get("title") or "", "url": a.get("url") or "",
             "source": (a.get("source") or {}).get("name") or (a.get("source") or {}).get("domain") or "",
             "published_at": a.get("published_at")} for a in out.get("data") or []]


def check(cluster):
    key = os.environ.get("CONTEXT_DEV_API_KEY", "").strip()
    if not key:
        return []
    first, last = _when(cluster.get("first_seen")), _when(cluster.get("last_seen"))
    start, end = (first - MARGIN, last + MARGIN) if first and last else (None, None)
    results = []
    for i, item in enumerate((cluster.get("top_items") or [])[:ITEMS], 1):
        q = _query(item)
        if not q:
            continue
        try:
            articles = _search(key, q, start, end)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            results.append({"item": f"E{i}", "query": q, "articles": [], "error": type(e).__name__})
            continue
        results.append({"item": f"E{i}", "query": q, "articles": articles,
                        "window": [start.date().isoformat(), end.date().isoformat()] if start else None})
    return results


def as_evidence(news):
    """Lines for the model's evidence, ids N1..; the model must judge whether each hit is really related."""
    if not news:
        return ["News check: not run (no checkable shared items, or no Context.dev key)."]
    lines = ["News check (Context.dev news search for the most shared items, in the window the group was active ±2 days; "
             "results are search hits, not confirmed matches):"]
    n = 0
    for r in news:
        if r.get("error"):
            lines.append(f"  for {r['item']}: the search failed")
        elif not r["articles"]:
            lines.append(f"  for {r['item']}: no news articles found in that window")
        for a in r["articles"]:
            n += 1
            lines.append(f"  N{n} (for {r['item']}): {a['title'][:160]!r}, {a['source']}, {(a['published_at'] or '?')[:10]}")
    return lines
