"""Plain-language explanation of one cluster the core found, written by a language model (Gemini).

Team rule (CLAUDE.md): a language model may EXPLAIN a cluster the core found, never find or overrule one.
So the model only gets the evidence the core already produced, must cite it, must list innocent
explanations, and gives no verdict. The page labels the answer as AI-generated.

Privacy: usernames are replaced by "Member 1..n" and @handles in texts by "@someone" before anything
leaves the server. Only the cluster's own evidence is sent, never whole histories.

    explanation = explain(cluster, source)      # dict, or raises ExplainError

Needs GEMINI_API_KEY in the environment (server .env). Model: GEMINI_MODEL, default gemini-flash-latest.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")   # gemini-2.5-flash is closed to new keys (404)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_ITEMS = 12          # shared items sent as evidence
MAX_TEXT = 400          # characters per item
PER_HOUR = 60           # explanations per hour for the whole site (cost guard)

_cache = {}
_lock = threading.Lock()
_calls = []

ACTIVITIES = ["amplifying a link", "pushing a message or narrative", "karma or follower farming",
              "spam or product promotion", "automated news or content feed", "organised campaign by real people",
              "community of real people talking to each other", "unclear"]

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Two or three plain sentences: what this group appears to do, with the main evidence."},
        "likely_activity": {"type": "string", "enum": ACTIVITIES},
        "observations": {"type": "array", "items": {"type": "object", "properties": {
            "point": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}, "description": "Evidence ids such as E1, F2."}},
            "required": ["point", "evidence"]}},
        "innocent_explanations": {"type": "array", "items": {"type": "object", "properties": {
            "explanation": {"type": "string"},
            "plausibility": {"type": "string", "enum": ["low", "medium", "high"]},
            "why": {"type": "string"}}, "required": ["explanation", "plausibility", "why"]}},
        "what_to_check_next": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "string", "description": "What the evidence cannot show."},
    },
    "required": ["summary", "likely_activity", "observations", "innocent_explanations", "what_to_check_next", "uncertainty"],
}

INSTRUCTIONS = """You explain the evidence behind one group of social-media accounts that a statistical detector linked
because they share the same content (texts, links, reposts, replies) far more often than chance predicts.

Rules:
- Use ONLY the evidence given. Cite evidence ids (E1, F1, ...) for every observation. Do not invent facts, dates, names, motives or links.
- Describe what the group APPEARS to be doing, for example amplifying one link, repeating one message or narrative,
  farming karma by copying old comments, promoting a product, or running an automated feed.
- Always weigh innocent explanations: an automated news or weather feed, a real campaign or fan group, people who
  answer each other in one community, everyone sharing one piece of breaking news, a common short phrase.
  Rate each one low / medium / high with a reason taken from the evidence.
- No verdict. Never say the accounts ARE bots or trolls; say what the evidence suggests and how strongly.
- Never speculate about who is behind the group or about individual people. Members are numbered on purpose.
- If the shared content is political, describe the message neutrally; do not take sides.
- Plain English, short sentences, for a moderator who is not a statistician."""


class ExplainError(Exception):
    pass


def _pseudonymise(cluster):
    names = {a["username"]: f"Member {i + 1}" for i, a in enumerate(cluster.get("accounts") or [])}

    def clean(text):
        text = re.sub(r"(?<![\w/])@[\w.\-]{2,}", "@someone", text or "")
        text = re.sub(r"(?<![\w/])u/[\w-]{3,}", "u/someone", text)
        for real, alias in names.items():
            if len(real) >= 3:
                text = text.replace(real, alias)
        return text[:MAX_TEXT]
    return names, clean


def build_evidence(cluster, source):
    """The cluster's evidence as plain lines with ids; nothing that identifies a person."""
    names, clean = _pseudonymise(cluster)
    lines = [f"Platform / data: {source.get('comments_file') or 'uploaded data'}"
             + (" (SYNTHETIC test data)" if source.get("synthetic") else ""),
             f"Group: {cluster['size']} accounts, confidence {cluster['confidence']} "
             "(average share of each member's own content that another member also has; 0 to 1, not a probability)",
             f"Active from {cluster.get('first_seen') or 'unknown'} to {cluster.get('last_seen') or 'unknown'}"]
    shares = sorted((a.get("copied_share") or 0) for a in cluster.get("accounts") or [])
    if shares:
        lines.append(f"F1: members' own copied share: lowest {shares[0]:.2f}, median {shares[len(shares) // 2]:.2f}, highest {shares[-1]:.2f}")
    gap = cluster.get("copy_gap_seconds")
    if gap:
        lines.append(f"F2: copies follow each other after a median of {gap['median']:.0f} seconds (over {gap['items']} shared items)")
    created = cluster.get("created_within_30_days")
    if created:
        lines.append(f"F3: {created['accounts']} of {created['of']} accounts with a known creation date were created within one 30-day window")
    auto = cluster.get("declared_automation")
    lines.append(f"F4: {auto['accounts']} of {auto['of']} accounts say in their name or bio that they are automated (bot, feed, RSS)"
                 if auto else "F4: no member says it is automated")
    kinds = {}
    for e in cluster.get("edges") or []:
        kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    lines.append(f"F5: links between members by kind of shared content: {kinds} (of {cluster.get('edge_count')} linked pairs)")
    lines.append("Most widely shared items (kind, how many members, first and last time seen, value):")
    for i, it in enumerate((cluster.get("top_items") or [])[:MAX_ITEMS], 1):
        lines.append(f"E{i}: {it.get('kind')}, {it.get('accounts')} members, {it.get('first_seen') or '?'} .. "
                     f"{it.get('last_seen') or '?'}: {clean(it.get('value'))!r}")
    return "\n".join(lines)


def _call_gemini(evidence):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ExplainError("Explanations are not configured on this server (GEMINI_API_KEY is missing).")
    body = {
        "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
        "contents": [{"role": "user", "parts": [{"text": "Evidence:\n" + evidence}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048,
                             "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    req = urllib.request.Request(API.format(model=MODEL), data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(2 + 3 * attempt)
                continue
            raise ExplainError(f"The language model answered with error {e.code}. Try again in a minute.") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(2)
                continue
            raise ExplainError("The language model did not answer. Try again in a minute.") from None
    try:
        text = out["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError):
        reason = ((out.get("candidates") or [{}])[0]).get("finishReason") or (out.get("promptFeedback") or {}).get("blockReason")
        raise ExplainError(f"The language model gave no usable answer ({reason or 'unknown reason'}).") from None


def explain(cache_key, cluster, source):
    """Explanation for one cluster, cached by cache_key (e.g. ('shared', result id, cluster id))."""
    with _lock:
        if cache_key in _cache:
            return _cache[cache_key]
        now = time.time()
        _calls[:] = [t for t in _calls if now - t < 3600]
        if len(_calls) >= PER_HOUR:
            raise ExplainError(f"This demo allows {PER_HOUR} explanations per hour. Try again later.")
        _calls.append(now)
    evidence = build_evidence(cluster, source)
    t0 = time.time()
    answer = _call_gemini(evidence)
    result = {"model": MODEL, "seconds": round(time.time() - t0, 1), "explanation": answer,
              "evidence_sent": evidence}
    with _lock:
        _cache[cache_key] = result
    return result
