"""Plain-language explanation of one cluster the core found, written by a language model (Gemini).

Team rule (CLAUDE.md): a language model may EXPLAIN a cluster the core found, never find or overrule one.
So the model only gets the evidence the core already produced, must cite it, must list innocent
explanations, and gives no verdict. The page labels the answer as AI-generated.

Privacy: usernames are replaced by "Member 1..n" and @handles in texts by "@someone" before anything
leaves the server. Only the cluster's own evidence is sent, never whole histories.

    explanation = explain(cluster, source)      # dict, or raises ExplainError

Provider: Hostinger AI Router (OpenAI-compatible, HOSTINGER_ROUTER_API_KEY; model ROUTER_MODEL, default
gemini-3.5-flash-eu, run in the EU) first; Google's Gemini API (GEMINI_API_KEY, GEMINI_MODEL) as fallback.
Keys live only in the server's .env.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import newscheck

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")   # gemini-2.5-flash is closed to new keys (404)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ROUTER = os.environ.get("HOSTINGER_ROUTER_BASE_URL", "https://router.hostinger.com/v1").rstrip("/")
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gemini-3.5-flash-eu")
UA = "spot-the-swarm/1.0 (Junction 2026 hackathon)"   # Cloudflare in front of the router refuses Python's default (error 1010)
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
- If a news check is given (N1, N2, ...), use it for the breaking-news explanation: say whether the hits are really about the
  same thing as the shared items and cite them; search hits that are about something else are not evidence.
- Always weigh innocent explanations: an automated news or weather feed, a real campaign or fan group, people who
  answer each other in one community, everyone sharing one piece of breaking news, a common short phrase.
  Rate each one low / medium / high with a reason taken from the evidence.
- No verdict. Never say the accounts ARE bots or trolls; say what the evidence suggests and how strongly.
- The tool is for monitoring: flagged accounts are worth watching, not proven bots, and some of them are real people.
  Say so once, and never suggest banning, suspending or restricting anyone; suggest watching and checking instead.
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
    accounts = cluster.get("accounts") or []
    flagged = sum(1 for a in accounts if a.get("flagged", True))
    if accounts:
        lines.append(f"F6: {flagged} of {len(accounts)} members are flagged (own copied share at least half the group's confidence); "
                     + (f"the other {len(accounts) - flagged} are only linked by a few shared items and are NOT flagged, "
                        "so describe them as linked, never as part of the swarm's behaviour" if flagged < len(accounts) else "all are flagged"))
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


def _call_gemini(evidence, instructions=INSTRUCTIONS, schema=SCHEMA):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ExplainError("Explanations are not configured on this server (GEMINI_API_KEY is missing).")
    body = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": [{"role": "user", "parts": [{"text": "Evidence:\n" + evidence}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json", "responseSchema": schema},
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


def _call_router(evidence, instructions=INSTRUCTIONS, schema=SCHEMA):
    """Hostinger AI Router, OpenAI chat completions with a JSON schema. -> (answer, model label)"""
    key = os.environ.get("HOSTINGER_ROUTER_API_KEY", "").strip()
    if not key:
        raise ExplainError("Hostinger AI Router is not configured (HOSTINGER_ROUTER_API_KEY is missing).")
    body = {
        "model": ROUTER_MODEL,
        "messages": [{"role": "system", "content": instructions},
                     {"role": "user", "content": "Evidence:\n" + evidence}],
        "temperature": 0.2,
        "max_tokens": 4096,   # the model also spends tokens on reasoning before the answer
        "response_format": {"type": "json_schema", "json_schema": {"name": "swarm_explanation", "schema": schema}},
    }
    req = urllib.request.Request(ROUTER + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 1:
                time.sleep(3)
                continue
            raise ExplainError(f"Hostinger AI Router answered with error {e.code}.") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < 1:
                time.sleep(2)
                continue
            raise ExplainError("Hostinger AI Router did not answer.") from None
    try:
        text = out["choices"][0]["message"]["content"]
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        return json.loads(text), f"{ROUTER_MODEL} via Hostinger AI Router"
    except (KeyError, IndexError, TypeError, ValueError):
        raise ExplainError("Hostinger AI Router gave no usable answer.") from None


def _answer(evidence, instructions=INSTRUCTIONS, schema=SCHEMA):
    """Router first, Gemini directly as fallback. -> (answer, model label, note about the fallback or None)"""
    errors = []
    if os.environ.get("HOSTINGER_ROUTER_API_KEY", "").strip():
        try:
            answer, label = _call_router(evidence, instructions, schema)
            return answer, label, None
        except ExplainError as e:
            errors.append(str(e))
    if os.environ.get("GEMINI_API_KEY", "").strip():
        answer = _call_gemini(evidence, instructions, schema)
        return answer, f"{MODEL} via Google Gemini API", ("; ".join(errors) + " Used Google's Gemini API instead.") if errors else None
    raise ExplainError(errors[0] if errors else "Explanations are not configured on this server (no language-model key).")


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One sentence: what this analysis found, for someone who has not seen it."},
        "summary": {"type": "string", "description": "Three to five plain sentences on the whole result, citing evidence ids."},
        "swarms": {"type": "array", "items": {"type": "object", "properties": {
            "swarm": {"type": "string", "description": "The swarm label, e.g. S1."},
            "appears_to": {"type": "string", "description": "One short sentence: what this group appears to do."},
            "likely_activity": {"type": "string", "enum": ACTIVITIES},
            "strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
            "evidence": {"type": "array", "items": {"type": "string"},
                         "description": "Evidence ids only, such as S1 or S1.E2; never quote the evidence here."}},
            "required": ["swarm", "appears_to", "likely_activity", "strength", "evidence"]}},
        "how_to_read": {"type": "string", "description": "One or two sentences on what the result does and does not mean."},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "summary", "swarms", "how_to_read", "next_steps"],
}

RESULT_INSTRUCTIONS = """You explain the WHOLE result of a statistical detector that looks for groups of social-media accounts
sharing the same content (texts, links, reposts, replies) far more often than chance predicts. You get the run's summary and
a short evidence block per group (S1, S2, ...). Write for a moderator or journalist who is not a statistician.

Rules:
- Use ONLY the evidence given; cite ids (R1, S1, S1.E1, ...). Do not invent facts, names, motives or links.
- If no group was found, explain plainly that this is the expected answer for an ordinary discussion and what the detector
  could and could not have seen (signals used, number of accounts and comments); never hint that something is hidden.
- For each group say what it APPEARS to do and how strong the evidence is, judged from the evidence as a whole (how many
  items are shared, how fast copies follow each other, accounts created together), NOT from the confidence number alone:
  confidence is how much of the members' posts the group shares, not a probability, and a real botnet that also posts its own
  generated text can have a low confidence. A group whose members say they are automated,
  or that shares news headlines, may be a harmless feed: say so.
- Members that are linked but not flagged are not accused; never describe them as part of a swarm.
- No verdict. Never say accounts ARE bots or trolls. No speculation about who is behind a group. Political content: neutral.
- The tool is for monitoring: in how_to_read, say that flagged accounts are worth watching, not proven bots, that some of
  them are real people, and that the result is for monitoring accounts, never for banning or restricting them. Next steps
  are things to watch or check, never bans, suspensions or restrictions.
- If the data is synthetic, say so in the headline.
- Plain English, short sentences."""

MAX_RESULT_SWARMS = 10


def build_result_evidence(result):
    """The whole result as plain lines with ids; usernames never leave the server (only counts and item texts)."""
    src = result.get("source") or {}
    clusters = result.get("clusters") or []
    signals = result.get("signals") or {}
    used = [k for k, s in signals.items() if s.get("status") == "used"]
    skipped = [k for k, s in signals.items() if s.get("status") != "used"]
    lines = [f"R1: data: {src.get('comments_file') or 'uploaded data'}" + (" (SYNTHETIC test data)" if src.get("synthetic") else ""),
             f"R2: {src.get('comments')} comments by {src.get('accounts')} accounts",
             f"R3: signals used: {', '.join(used) or 'none'}; skipped: {', '.join(skipped) or 'none'}",
             f"R4: {len(clusters)} groups found at confidence {((result.get('parameters') or {}).get('min_confidence'))} or more"]
    at = ((result.get("metrics") or {}).get("at_min_confidence")) or {}
    if at.get("precision") is not None:
        lines.append(f"R5: measured against labels in the data: precision {at['precision']}, recall {at['recall']}, "
                     f"false-positive rate {at['false_positive_rate']} (the cut was chosen with labels visible)")
    for i, c in enumerate(clusters[:MAX_RESULT_SWARMS], 1):
        _, clean = _pseudonymise(c)
        accounts = c.get("accounts") or []
        flagged = sum(1 for a in accounts if a.get("flagged", True))
        parts = [f"S{i}: {c['size']} accounts ({flagged} flagged, {len(accounts) - flagged} only linked), confidence {c['confidence']}"]
        gap = c.get("copy_gap_seconds")
        if gap:
            parts.append(f"copies follow each other after a median of {gap['median']:.0f} s")
        created = c.get("created_within_30_days")
        if created:
            parts.append(f"{created['accounts']} of {created['of']} created within one 30-day window")
        auto = c.get("declared_automation")
        if auto:
            parts.append(f"{auto['accounts']} of {auto['of']} say they are automated")
        lines.append("; ".join(parts))
        for j, it in enumerate((c.get("top_items") or [])[:3], 1):
            lines.append(f"S{i}.E{j}: {it.get('kind')}, {it.get('accounts')} members: {clean(it.get('value'))[:200]!r}")
    if len(clusters) > MAX_RESULT_SWARMS:
        lines.append(f"(and {len(clusters) - MAX_RESULT_SWARMS} more groups not listed)")
    return "\n".join(lines)


def explain_result(cache_key, result):
    """Plain-language explanation of a whole result, cached by cache_key. Same provider, privacy and rate limit as explain()."""
    with _lock:
        if cache_key in _cache:
            return _cache[cache_key]
        now = time.time()
        _calls[:] = [t for t in _calls if now - t < 3600]
        if len(_calls) >= PER_HOUR:
            raise ExplainError(f"This demo allows {PER_HOUR} explanations per hour. Try again later.")
        _calls.append(now)
    t0 = time.time()
    evidence = build_result_evidence(result)
    answer, label, note = _answer(evidence, RESULT_INSTRUCTIONS, RESULT_SCHEMA)
    out = {"model": label, "seconds": round(time.time() - t0, 1), "explanation": answer, "evidence_sent": evidence, "note": note}
    with _lock:
        _cache[cache_key] = out
    return out


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
    t0 = time.time()
    news = [] if source.get("synthetic") else newscheck.check(cluster)   # simulated texts are never in the news
    evidence = build_evidence(cluster, source) + "\n" + "\n".join(
        newscheck.as_evidence(news) if not source.get("synthetic") else ["News check: skipped (synthetic data)."])
    answer, label, note = _answer(evidence)
    result = {"model": label, "seconds": round(time.time() - t0, 1), "explanation": answer,
              "evidence_sent": evidence, "note": note, "news": news}
    with _lock:
        _cache[cache_key] = result
    return result
