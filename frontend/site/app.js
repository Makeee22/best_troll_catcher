// Dashboard for the API in docs/api.md, plus POST /api/analyze (upload) and the discussion jobs (frontend/api/).
// No build step, no dependencies. All server text goes in through textContent.
// Layout: a start screen (supported sites + one input) that moves to the top once a result is shown;
// the result is a column of windows that can be folded with the arrow in their title bar.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || window.SWARM_API_BASE || "").replace(/\/+$/, "");
const MAX_BYTES = 20 * 1024 * 1024; // both files together; same limit as the API and nginx
const MAX_EDGE_ROWS = 100;
const MAX_PAGE_BYTES = 100 * 1024 * 1024; // a saved Reddit page; same limit as MAX_PAGE_BYTES in api/jobs.py and nginx
const TOP_ITEMS_SHOWN = 3;

const $ = (id) => document.getElementById(id);

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) el.append(child);
  }
  return el;
}

// replaceChildren(null) would insert the text "null"; drop empty parts like h() does (optional parts are written as `x ? node : null`).
const nativeReplace = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...children) {
  return nativeReplace.apply(this, children.flat().filter((c) => c != null && c !== false));
};

function svg(tag, attrs, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, value);
  el.append(...children);
  return el;
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(API + path, options);
  } catch (e) {
    throw new Error("Cannot reach the server. Check the connection and try again.");
  }
  let body = null;
  try { body = await response.json(); } catch (e) { /* not JSON, e.g. an nginx error page */ }
  if (!response.ok) {
    const error = new Error(errorText(response.status, body));
    error.status = response.status;
    throw error;
  }
  if (body === null) throw new Error("The server answered with something that is not JSON.");
  return body;
}

function errorText(status, body) {
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  if (status === 413) return "The files are too large (limit 20 MB together).";
  if (status === 502 || status === 504) return "The analysis took too long or the server restarted. Try a smaller file.";
  return "The server answered with error " + status + ".";
}

const fmtTime = (iso) => {
  if (!iso) return "unknown time";
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
};
const fmtDay = (iso) => {
  if (!iso) return "?";
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toISOString().slice(0, 10);
};
const fmtPct = (x) => (x == null ? "n/a" : (x * 100).toFixed(1) + " %");
const fmtPct0 = (x) => (x == null ? "n/a" : Math.round(x * 100) + "%");
const fmtInt = (n) => (typeof n === "number" ? n.toLocaleString("en-GB") : "n/a");
const fmtConf = (x) => (typeof x === "number" ? x.toFixed(2) : "n/a");
const plural = (n, one, many) => fmtInt(n) + " " + (n === 1 ? one : many);
const KIND = { text: "Same text", link: "Same link", repost: "Reposted the same post",
               reply: "Replied to the same post", similar_text: "Nearly the same text",
               created_together: "Created close together (adds to the links above, never links alone)" };
const KIND_ICON = { text: "❝", link: "🔗", repost: "⟳", reply: "↩", similar_text: "≈", created_together: "◷" };
const kindName = (k) => KIND[k] || String(k);
// docs/api.md: a member is flagged when its own copied share is high enough; the others are linked, not accused.
// Results made before 14.11 evening have no "flagged" field: every member counted as flagged then.
const isFlagged = (a) => a.flagged !== false;

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function setBusy(text) {
  $("status").textContent = text || "";
  for (const id of ["analyse", "comments-file", "profiles-file"]) $(id).disabled = !!text;
}

// Handoff S6: no "weak" band. A pure botnet can sit at 0.24-0.28 (Test F, Fox8-23: its own generated text dilutes
// the copied share), so a low confidence is not a sign of innocent members. Say only what the number is.
const CONF_NOTE = "Confidence is how much of their posts the group shares, not a probability.";

function confidenceBar(x) {
  const value = typeof x === "number" ? Math.max(0, Math.min(1, x)) : 0;
  return h("span", { class: "conf", title: "confidence " + fmtConf(x) + ". " + CONF_NOTE },
    h("span", { class: "conf-bar" }, h("span", { style: "width:" + (value * 100).toFixed(0) + "%" })),
    h("span", { class: "conf-num" }, fmtConf(x)));
}

// ---- windows: the arrow in the title bar folds a window ----

function makeFoldable(section) {
  const bar = section.querySelector(".win-bar");
  const body = section.querySelector(".win-body");
  if (!bar || !body || bar.querySelector(".fold")) return;
  if (!body.id) body.id = section.id + "-body";
  const button = h("button", { type: "button", class: "fold", "aria-expanded": "true", "aria-controls": body.id,
                               title: "Hide this window" },
    h("span", { class: "sr-only" }, "Fold " + (bar.textContent || "").trim()),
    h("span", { "aria-hidden": "true", class: "fold-arrow" }, "▲"));
  button.addEventListener("click", () => setFolded(section, button.getAttribute("aria-expanded") === "true"));
  bar.append(button);
}

function setFolded(section, folded) {
  const button = section.querySelector(".fold");
  section.classList.toggle("folded", folded);
  section.querySelector(".win-body").hidden = folded;
  if (button) {
    button.setAttribute("aria-expanded", String(!folded));
    button.title = folded ? "Show this window" : "Hide this window";
  }
}

document.querySelectorAll("#results .win").forEach(makeFoldable);

// ---- start screen <-> result view ----

function enterResultView() {
  if (document.body.classList.contains("has-result")) return;
  document.body.classList.remove("home");
  document.body.classList.add("has-result");
  closeModeMenu();
}

function goHome() {
  loadToken++;
  if (jobIdFromHash()) history.replaceState(null, "", location.pathname + location.search);
  $("results").hidden = true;
  document.body.classList.remove("has-result");
  document.body.classList.add("home");
  $("synthetic-badge").hidden = true;
  setJobBusy(false);
  setBusy("");
  jobStatus();
  jobError("");
  showError("");
  scrollTo(0, 0);
  $("url-input").focus();
}
$("home-link").addEventListener("click", goHome);

// ---- loading ----

let details = new Map(); // swarm id -> detail object
let loadToken = 0;       // ignore answers that belong to an older result

// Where a result's details come from: the shared result, or one discussion job (link, Reddit page).
const SHARED = {
  job: null,
  explainResult: () => api("/api/explain", { method: "POST" }),
  detail: (id) => api("/api/swarms/" + encodeURIComponent(id)),
  explain: (id) => api("/api/swarms/" + encodeURIComponent(id) + "/explain", { method: "POST" }),
  metrics: () => api("/api/metrics"),
};
let ctx = SHARED;

function jobContext(job) {
  const base = "/api/jobs/" + encodeURIComponent(job.id) + "/swarms/";
  return {
    job,
    explainResult: () => api("/api/jobs/" + encodeURIComponent(job.id) + "/explain", { method: "POST" }),
    detail: (id) => api(base + encodeURIComponent(id)),
    explain: (id) => api(base + encodeURIComponent(id) + "/explain", { method: "POST" }),
    metrics: () => Promise.resolve(job.metrics || { source: job.listing.source, metrics: null }),
  };
}

async function showResult(listing, context) {
  const token = ++loadToken;
  ctx = context || SHARED;
  details = new Map();
  explained.clear();
  enterResultView();
  $("results").hidden = false;
  document.querySelectorAll("#results .win").forEach((w) => setFolded(w, false));
  const any = listing.swarms.length > 0;
  for (const id of ["win-map", "win-swarms", "win-flagged"]) $(id).hidden = !any;
  $("win-metrics").hidden = true;
  renderJobBanner(ctx.job);
  renderSourceLine(listing, ctx.job);
  renderSummary(listing, null);
  renderHeadline(listing, null);
  renderWarnings(listing.warnings || []);
  renderSignals(listing.signals || {}, listing.parameters || {});
  $("flagged").replaceChildren(h("p", { class: "muted" }, "Loading accounts…"));
  $("detail").replaceChildren();
  swarmOrder = listing.swarms.map((s) => s.id);
  renderSwarmList(listing.swarms);
  renderResultExplainBox(listing);
  $("swarm-map").replaceChildren(h("p", { class: "muted" }, "Drawing…"));
  scrollTo(0, 0);

  ctx.metrics().then(
    (m) => { if (token === loadToken) renderMetrics(m, listing.parameters || {}); },
    () => { /* no metrics: the window stays hidden */ }
  );

  try {
    const ids = listing.swarms.map((s) => s.id);
    for (let i = 0; i < ids.length; i += 6) { // a few at a time
      const batch = await Promise.all(ids.slice(i, i + 6).map((id) => ctx.detail(id)));
      if (token !== loadToken) return;
      batch.forEach((d) => details.set(d.id, d));
    }
  } catch (e) {
    if (token !== loadToken) return;
    $("flagged").replaceChildren(h("p", { class: "error" }, e.status === 404
      ? "The result on the server changed while loading (someone else uploaded files). Reload the page or upload again."
      : e.message));
    return;
  }
  const flagged = countFlagged();
  renderSummary(listing, flagged);
  renderHeadline(listing, flagged);
  renderFlagged(listing.swarms);
  if (any) {
    $("swarm-map").replaceChildren(renderSwarmMap(listing.swarms));
    selectSwarm(listing.swarms[0].id, false);
  }
}

// ---- colours per swarm (same colour on the map, in the list and in the graph) ----
let swarmOrder = [];
const PALETTE = ["#a98ce0", "#5fd9b8", "#f2e15a", "#ff8fc8", "#7fb2ff", "#ffaa66", "#b8e86a", "#d08cf0"];
const swarmColor = (id) => PALETTE[Math.max(0, swarmOrder.indexOf(id)) % PALETTE.length];
const swarmNumber = (id) => swarmOrder.indexOf(id) + 1;

// ---- overview ----

function renderHeadline(listing, flagged) {
  const n = listing.swarms.length;
  const el = $("headline");
  el.className = "headline " + (n ? "found" : "none");
  if (!n) {
    el.replaceChildren(h("span", { class: "headline-icon", "aria-hidden": "true" }, "✓"),
      h("span", null, "No swarms found. ", h("small", null, "No group of accounts here shares content more than chance explains.")));
    return;
  }
  el.replaceChildren(h("span", { class: "headline-icon", "aria-hidden": "true" }, "!"),
    h("span", null, plural(n, "swarm", "swarms") + " found" +
      (flagged != null ? ": " + plural(flagged, "account acts", "accounts act") + " as one" : "") + "."));
}

function renderSourceLine(listing, job) {
  const t = (job && job.thread) || {};
  const src = listing.source || {};
  let text;
  if (job) {
    const where = t.platform === "Reddit" ? "Reddit" + (t.subreddit ? " · " + t.subreddit : "") : (t.platform || "Discussion");
    const title = t.title ? "“" + t.title + "”" : (t.url || "");
    text = where + (t.author ? " · @" + t.author : "") + (title ? ": " + title : "");
  } else {
    text = [src.comments_file, src.profiles_file].filter(Boolean).join(" + ") || "Uploaded data";
  }
  $("source-line").textContent = text;
}

function renderSummary(listing, flagged) {
  const src = listing.source || {};
  const synthetic = src.synthetic === true;
  $("synthetic-badge").hidden = !synthetic;
  $("synthetic-note").hidden = !synthetic;
  const tile = (label, value, cls) => h("div", cls ? { class: cls } : null, h("dd", null, value), h("dt", null, label));
  $("summary").replaceChildren(
    tile("swarms", fmtInt(listing.swarms.length), listing.swarms.length ? "hot" : null),
    tile("flagged accounts", flagged == null ? "…" : fmtInt(flagged), flagged ? "hot" : null),
    tile("accounts read", fmtInt(src.accounts)),
    tile("comments read", fmtInt(src.comments))
  );
}

function renderWarnings(warnings) {
  $("warnings").replaceChildren(...(warnings.length
    ? [h("h3", null, "Notes about the input"), h("ul", { class: "warnings" }, warnings.map((w) => h("li", null, String(w))))]
    : []));
}

function renderSignals(signals, params) {
  const rows = Object.entries(signals).map(([kind, s]) => h("tr", null,
    h("td", null, kindName(kind)),
    h("td", null, s.status === "used" ? "used" : h("span", { class: "muted" }, "skipped: " + (s.reason || ""))),
    h("td", { class: "num" }, fmtInt(s.items)),
    h("td", { class: "num" }, fmtInt(s.links))));
  $("signals").replaceChildren(
    h("h3", null, "Signals"),
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Signal"), h("th", null, "Status"),
        h("th", { class: "num" }, "Shared items"), h("th", { class: "num" }, "Linked pairs"))),
      h("tbody", null, rows))),
    h("p", { class: "muted" },
      "Settings: texts of at least " + params.min_words + " words; a pair needs at least " + params.min_shared +
      " shared items" + (params.long_words ? " (or one shared text of at least " + params.long_words + " words)" : "") +
      " and must pass the chance test (false discovery rate " + params.alpha + "); groups of at least " +
      params.min_size + " accounts; swarms shown from confidence " + params.min_confidence + "." +
      (params.similar_text ? " The similar-text layer was on." : "")));
}

// ---- the swarm map: every swarm as a cluster of dots (phyllotaxis), one dot per account ----
const MAP_MAX_DOTS = 400;

function renderSwarmMap(swarms) {
  const W = 900, PAD = 24, GAP = 70;
  const blobs = swarms.map((s, i) => {
    const d = details.get(s.id);
    const members = d ? [...d.accounts].sort((a, b) => (isFlagged(b) - isFlagged(a)) || (b.copied_share - a.copied_share)) : [];
    const shown = members.slice(0, MAP_MAX_DOTS);
    const n = Math.max(1, shown.length);
    const step = n > 150 ? 5.5 : n > 40 ? 9 : 17;
    const dot = n > 150 ? 2.2 : n > 40 ? 3.8 : 7;
    const R = Math.max(62, step * Math.sqrt(n) + dot + 10);
    return { s, i, members, shown, step, dot, R };
  });
  let x = PAD, y = PAD, rowH = 0;
  for (const b of blobs) {
    const w = 2 * b.R, hgt = 2 * b.R + 34;
    if (x + w > W - PAD && x > PAD) { x = PAD; y += rowH + GAP; rowH = 0; }
    b.cx = x + b.R; b.cy = y + b.R; x += w + GAP; rowH = Math.max(rowH, hgt);
  }
  const rows = new Map();
  for (const b of blobs) { const k = Math.round(b.cy - b.R); (rows.get(k) || rows.set(k, []).get(k)).push(b); }
  for (const row of rows.values()) {
    const right = Math.max(...row.map((b) => b.cx + b.R));
    const shift = (W - PAD - right) / 2;
    row.forEach((b) => { b.cx += shift; });
  }
  const H = y + rowH + PAD;
  const root = svg("svg", { class: "swarm-map", viewBox: "0 0 " + W + " " + H, role: "img",
    "aria-label": swarms.length + " swarms drawn as clusters of dots; the list below has the same data." });
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (const b of blobs) {
    const color = swarmColor(b.s.id);
    const g = svg("g", { class: "blob", tabindex: "0", role: "button",
      "aria-label": "Swarm " + (b.i + 1) + ", " + b.s.size + " accounts, confidence " + fmtConf(b.s.confidence) + ". Show evidence." });
    const open = () => selectSwarm(b.s.id, true);
    g.addEventListener("click", open);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    g.append(svg("circle", { class: "halo", cx: b.cx, cy: b.cy, r: b.R, style: "fill:" + color }));
    b.shown.forEach((a, k) => {
      const r = b.step * Math.sqrt(k + 0.5), t = k * golden;
      const px = b.cx + r * Math.cos(t), py = b.cy + r * Math.sin(t);
      g.append(isFlagged(a)
        ? svg("circle", { cx: px.toFixed(1), cy: py.toFixed(1), r: b.dot, style: "fill:" + color })
        : svg("circle", { class: "linked-dot", cx: px.toFixed(1), cy: py.toFixed(1), r: b.dot }));
    });
    const flagged = b.members.filter(isFlagged).length;
    const label = svg("text", { x: b.cx, y: b.cy + b.R + 18, "text-anchor": "middle", class: "blob-label" });
    label.textContent = "Swarm " + (b.i + 1) + " · " + (flagged < b.members.length ? flagged + "/" : "") + b.s.size + " accounts";
    const sub = svg("text", { x: b.cx, y: b.cy + b.R + 34, "text-anchor": "middle", class: "blob-sub" });
    sub.textContent = (b.s.sample ? kindName(b.s.sample.kind).toLowerCase() + " · " : "") + "confidence " + fmtConf(b.s.confidence);
    const tip = svg("title");
    tip.textContent = "Swarm " + (b.i + 1) + ": " + b.s.size + " accounts, " + flagged + " flagged, confidence " + fmtConf(b.s.confidence) +
      (b.members.length > MAP_MAX_DOTS ? " (first " + MAP_MAX_DOTS + " drawn)" : "") +
      (b.s.sample ? "\nMost shared: " + String(b.s.sample.value).slice(0, 120) : "");
    g.append(tip, label, sub);
    root.append(g);
  }
  return h("div", { class: "map-wrap" }, root);
}

// ---- AI explanation of the whole result ----
const STRENGTH = { weak: "weak evidence", moderate: "moderate evidence", strong: "strong evidence" };

function renderResultExplainBox(listing) {
  if (!listing.swarms.length) { $("result-explain").replaceChildren(); return; }
  const box = h("div");
  const button = h("button", { type: "button", class: "ai-button" }, "✦ Explain this result with AI");
  button.addEventListener("click", async () => {
    button.disabled = true;
    box.replaceChildren(h("p", { class: "verdict pending" }, "Reading the evidence… (about 10–20 seconds)"));
    try {
      renderResultExplanation(box, await ctx.explainResult());
      button.hidden = true;
    } catch (e) {
      box.replaceChildren(h("p", { class: "error" }, e.message));
      button.disabled = false;
    }
  });
  $("result-explain").replaceChildren(
    h("div", { class: "ai-head" }, button, h("span", { class: "muted" }, "Plain-language summary. Never decides who is flagged.")),
    box);
}

function renderResultExplanation(box, answer) {
  const x = answer.explanation || {};
  const swarmIdFor = (label) => swarmOrder[parseInt(String(label).replace(/\D/g, ""), 10) - 1];
  box.replaceChildren(h("div", { class: "verdict explained result-ai" },
    x.headline ? h("p", { class: "ai-headline" }, x.headline) : null,
    x.summary ? h("p", null, x.summary) : null,
    (x.swarms || []).length ? h("ul", { class: "ai-swarms" }, x.swarms.map((s) => {
      const id = swarmIdFor(s.swarm);
      return h("li", { style: id ? "border-left-color:" + swarmColor(id) : "" },
        h("strong", null, (s.swarm || "").replace(/^S/, "Swarm ")), " ",
        h("span", { class: "strength strength-" + s.strength }, STRENGTH[s.strength] || s.strength), " ",
        s.appears_to, " ",
        id ? h("button", { type: "button", class: "link-button", onclick: () => selectSwarm(id, true) }, "Show evidence") : null);
    })) : null,
    h("details", { class: "more" }, h("summary", null, "More from the AI"),
      h("p", { class: "ai-label" }, "AI-generated (" + answer.model + ", " + answer.seconds + " s). It explains the detector's evidence; it is not a verdict."),
      x.how_to_read ? h("p", null, x.how_to_read) : null,
      (x.next_steps || []).length ? h("div", null, h("strong", null, "What to check next"), h("ul", null, x.next_steps.map((t) => h("li", null, t)))) : null,
      answer.note ? h("p", { class: "muted" }, answer.note) : null,
      h("p", null, h("strong", null, "What was sent to the model")),
      h("pre", null, answer.evidence_sent || ""))));
}

const countFlagged = () => new Set([...details.values()].flatMap((d) => d.accounts.filter(isFlagged).map((a) => a.username))).size;

// ---- flagged accounts ----

function renderFlagged(swarms) {
  if (!swarms.length) { $("flagged").replaceChildren(); return; }
  const all = [];
  const groups = swarms.map((s, i) => {
    const members = details.get(s.id).accounts;
    const accounts = members.filter(isFlagged);
    const linked = members.length - accounts.length;
    all.push(...accounts.map((a) => a.username));
    return h("div", { class: "group", style: "border-left-color:" + swarmColor(s.id) },
      h("div", { class: "group-head" },
        h("strong", null, "Swarm " + (i + 1)),
        h("span", { class: "muted" }, accounts.length + " flagged" + (linked ? " · " + linked + " only linked" : "")),
        h("button", { type: "button", class: "link-button", onclick: () => selectSwarm(s.id, true) }, "Evidence")),
      h("ul", { class: "chips" }, accounts.map((a) =>
        h("li", { title: "shares " + fmtPct(a.copied_share) + " of its own content with this group" }, a.username))));
  });
  const copy = h("button", { type: "button", class: "small-button", onclick: async () => {
    try { await navigator.clipboard.writeText(all.join("\n")); copy.textContent = "Copied"; }
    catch (e) { copy.textContent = "Copy failed"; }
  } }, "Copy all " + all.length + " names");
  $("flagged").replaceChildren(...groups, h("p", null, copy));
}

// ---- detection quality: only when the data has labels ----

function meter(label, value, good) {
  const v = typeof value === "number" ? Math.max(0, Math.min(1, value)) : 0;
  return h("div", { class: "meter" },
    h("div", { class: "meter-head" }, h("span", null, label), h("b", null, fmtPct0(value))),
    h("div", { class: "meter-bar " + (good ? "good" : "bad") }, h("span", { style: "width:" + (v * 100).toFixed(1) + "%" })));
}

function renderMetrics(data) {
  const m = data.metrics;
  if (!m) { $("win-metrics").hidden = true; return; }
  $("win-metrics").hidden = false;
  const at = m.at_min_confidence || {};
  const thresholds = (m.by_threshold || []).map((t) => h("tr", { class: t.min_confidence === at.min_confidence ? "current" : "" },
    h("td", null, "≥ " + t.min_confidence),
    h("td", { class: "num" }, fmtPct(t.precision)),
    h("td", { class: "num" }, fmtPct(t.recall)),
    h("td", { class: "num" }, fmtPct(t.false_positive_rate)),
    h("td", { class: "num" }, fmtInt(t.false_positives))));
  const labels = Object.entries(m.by_label || {}).map(([label, v]) => h("tr", null,
    h("td", null, label),
    h("td", { class: "num" }, fmtInt(v.accounts)),
    h("td", { class: "num" }, fmtInt(v.flagged)),
    h("td", { class: "num" }, fmtPct(v.accounts ? v.flagged / v.accounts : null))));
  $("metrics").replaceChildren(
    h("div", { class: "meters" },
      meter("Flagged that are bots (precision)", at.precision, true),
      meter("Bots that were found (recall)", at.recall, true),
      meter("Humans wrongly flagged", at.false_positive_rate, false)),
    h("p", { class: "muted" }, fmtInt(at.false_positives) + " innocent accounts flagged. Measured with the data's own labels." +
      (data.source && data.source.synthetic ? " Synthetic data: shows the code works, not real-world accuracy." : "")),
    h("details", { class: "more" }, h("summary", null, "All numbers"),
      h("p", { class: "note-plain" }, "Honesty note: the cut " + at.min_confidence + " is the one value chosen with the labels visible, so these numbers are " +
        "somewhat optimistic. Labels are only used to measure; detection never sees them."),
      h("div", { class: "scroll" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Confidence"), h("th", { class: "num" }, "Precision"),
          h("th", { class: "num" }, "Recall"), h("th", { class: "num" }, "False-positive rate"),
          h("th", { class: "num" }, "Innocent flagged"))),
        h("tbody", null, thresholds))),
      labels.length ? h("div", { class: "scroll" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Label"), h("th", { class: "num" }, "Accounts"),
          h("th", { class: "num" }, "Flagged"), h("th", { class: "num" }, "Share flagged"))),
        h("tbody", null, labels))) : null,
      m.labelled_without_content ? h("p", { class: "muted" }, fmtInt(m.labelled_without_content) + " labelled accounts had no usable content and are left out.") : null));
}

// ---- swarm list and evidence ----

function renderSwarmList(swarms) {
  $("swarm-list").replaceChildren(...swarms.map((s, i) =>
    h("button", { type: "button", class: "swarm-item", "aria-pressed": "false", "data-id": s.id, style: "border-left-color:" + swarmColor(s.id),
                  onclick: () => selectSwarm(s.id, false) },
      h("span", { class: "swarm-head" },
        h("strong", null, "Swarm " + (i + 1)),
        h("span", null, s.size + " accounts"),
        confidenceBar(s.confidence)),
      s.sample ? h("span", { class: "sample" }, (KIND_ICON[s.sample.kind] || "") + " “" + s.sample.value + "”") : null)));
}

// docs/api.md: a description, never a verdict; the cluster is never hidden or greyed out for it.
const automationNote = (a) => a.accounts + " of " + a.of + " say they are automated: a feed, or a swarm posing as one.";

function fmtGapSeconds(s) {
  if (s < 60) return Math.round(s) + " s";
  if (s < 7200) return Math.round(s / 60) + " min";
  if (s < 172800) return Math.round(s / 3600) + " h";
  return Math.round(s / 86400) + " days";
}

async function selectSwarm(id, scroll) {
  document.querySelectorAll(".swarm-item").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  const token = loadToken;
  let d = details.get(id);
  if (!d) {
    $("detail").replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try {
      d = await ctx.detail(id);
    } catch (e) {
      if (token === loadToken) $("detail").replaceChildren(h("p", { class: "error" }, e.status === 404
        ? "This swarm no longer exists on the server (the data changed). Reload the page."
        : e.message));
      return;
    }
    if (token !== loadToken) return;
    details.set(id, d);
  }
  renderDetail(d);
  if (scroll) {
    setFolded($("win-swarms"), false);
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// ---- AI explanation of one swarm (server side; explain.py). It explains the evidence, it never decides. ----

const explained = new Map(); // swarm id -> explanation answer, for this result

const PLAUS = { low: "unlikely", medium: "possible", high: "likely" };

function renderExplanation(box, answer) {
  const e = answer.explanation || {};
  const refs = (ids) => (ids && ids.length ? h("span", { class: "refs" }, " [" + ids.join(", ") + "]") : null);
  box.className = "verdict explained";
  box.replaceChildren(
    h("p", { class: "ai-headline" }, e.likely_activity || "What the group appears to do is unclear"),
    h("p", null, e.summary || ""),
    (e.innocent_explanations || []).length ? h("div", { class: "innocent" },
      h("p", null, h("strong", null, "Innocent explanations")),
      h("ul", null, e.innocent_explanations.map((x) => h("li", null,
        h("span", { class: "strength plaus-" + x.plausibility }, PLAUS[x.plausibility] || x.plausibility), " ", x.explanation)))) : null,
    h("details", { class: "more" }, h("summary", null, "More from the AI"),
      h("p", { class: "ai-label" }, "AI-written by " + answer.model + ". It can be wrong, and it does not change the result." + (answer.note ? " (" + answer.note + ")" : "")),
      (e.observations || []).length ? h("ul", null, e.observations.map((o) => h("li", null, o.point, refs(o.evidence)))) : null,
      (e.innocent_explanations || []).length ? h("ul", null, e.innocent_explanations.map((x) => h("li", null, x.explanation + ": ", h("span", { class: "muted" }, x.why)))) : null,
      (e.what_to_check_next || []).length ? h("div", null,
        h("p", null, h("strong", null, "What to check next")),
        h("ul", null, e.what_to_check_next.map((x) => h("li", null, x)))) : null,
      e.uncertainty ? h("p", { class: "muted" }, h("strong", null, "What the evidence cannot show: "), e.uncertainty) : null,
      renderNews(answer.news || []),
      h("p", null, h("strong", null, "Evidence sent to the model (usernames replaced)")),
      h("pre", null, answer.evidence_sent || "")));
}

// News check (Context.dev news search, server side): coverage of the most shared items while the group was active.
function renderNews(news) {
  if (!news.length) return null;
  let n = 0;
  return h("div", { class: "news" },
    h("p", null, h("strong", null, "News check"), h("span", { class: "muted" },
      " (Context.dev news search for the most shared items, ±2 days. Search hits, not confirmed matches.)")),
    h("ul", null, news.map((r) => h("li", null,
      h("span", { class: "muted" }, "For " + r.item + ": "),
      r.error ? "the search failed." : !r.articles.length ? "no news articles in that window." :
        h("ul", null, r.articles.map((a) => {
          n += 1;
          const link = /^https?:\/\//.test(a.url) ? h("a", { href: a.url, target: "_blank", rel: "noopener noreferrer" }, a.title || a.url) : (a.title || "");
          return h("li", null, h("span", { class: "refs" }, "N" + n + " "), link,
            h("span", { class: "muted" }, " · " + (a.source || "?") + (a.published_at ? " · " + a.published_at.slice(0, 10) : "")));
        }))))));
}

function renderExplainBox(d) {
  const box = h("div", { class: "ai-box" });
  if (explained.has(d.id)) { renderExplanation(box, explained.get(d.id)); return box; }
  const button = h("button", { type: "button", class: "ai-button" }, "✦ Explain this swarm with AI");
  const say = h("span", { class: "muted" }, " Weighs innocent look-alikes like breaking news. Usernames are hidden.");
  button.addEventListener("click", async () => {
    button.disabled = true;
    say.textContent = " Checking the news and asking the AI… about 15–30 s.";
    const token = loadToken;
    try {
      const answer = await ctx.explain(d.id);
      if (token !== loadToken) return;
      explained.set(d.id, answer);
      renderExplanation(box, answer);
    } catch (e) {
      button.disabled = false;
      say.textContent = " " + e.message;
    }
  });
  box.replaceChildren(h("p", { class: "ai-head" }, button, say));
  return box;
}

// One big-number card of evidence.
function stat(icon, value, label, title) {
  return h("div", { class: "stat", title: title || "" },
    h("span", { class: "stat-icon", "aria-hidden": "true" }, icon),
    h("span", { class: "stat-value" }, value),
    h("span", { class: "stat-label" }, label));
}

function renderDetail(d) {
  const edges = [...(d.edges || [])].sort((a, b) => b.shared - a.shared);
  const names = d.accounts.map((a) => a.username);
  const flagged = d.accounts.filter(isFlagged).length;
  const created = d.created_within_30_days;
  const gap = d.copy_gap_seconds;
  const shownEdges = edges.slice(0, MAX_EDGE_ROWS);
  const items = d.top_items || [];
  const number = swarmNumber(d.id) || d.id;
  const color = swarmColor(d.id);

  const stats = h("div", { class: "stats" },
    stat("◉", flagged + (flagged < d.size ? "/" + d.size : ""), flagged < d.size ? "flagged of the accounts" : "accounts, all flagged"),
    stat("◧", fmtConf(d.confidence), "confidence", CONF_NOTE),
    gap ? stat("⏱", fmtGapSeconds(gap.median), gap.median < 60 ? "between copies: automation speed" : "median time between copies",
      "Median over " + fmtInt(gap.items) + " shared items") : null,
    created ? stat("◷", created.accounts + "/" + created.of, "accounts created within 30 days", "Supporting evidence only; it does not change the confidence.") : null,
    d.declared_automation ? stat("⚙", d.declared_automation.accounts + "/" + d.declared_automation.of, "say they are automated", automationNote(d.declared_automation)) : null);

  $("detail").replaceChildren(
    h("div", { class: "detail-head", style: "border-left-color:" + color },
      h("h3", null, "Swarm " + number),
      h("span", { class: "muted" }, "active " + fmtDay(d.first_seen) + (d.last_seen && fmtDay(d.last_seen) !== fmtDay(d.first_seen) ? " – " + fmtDay(d.last_seen) : ""))),
    stats,
    d.declared_automation ? h("p", { class: "note" }, automationNote(d.declared_automation) + " Check the source.") : null,
    h("h4", null, "What they share most"),
    renderItems(items.slice(0, TOP_ITEMS_SHOWN)),
    items.length > TOP_ITEMS_SHOWN ? h("details", { class: "more" }, h("summary", null, (items.length - TOP_ITEMS_SHOWN) + " more shared items"),
      renderItems(items.slice(TOP_ITEMS_SHOWN))) : null,
    renderExplainBox(d),
    h("h4", null, "Who is linked to whom"),
    names.length <= 24
      ? renderGraph(names, edges, color, new Set(d.accounts.filter((a) => !isFlagged(a)).map((a) => a.username)))
      : h("p", { class: "muted" }, "Too many accounts for the picture; the tables below have them."),
    h("details", { class: "more" }, h("summary", null, "Members and how much each copies"),
      flagged < d.size ? h("p", { class: "muted" }, "Members that are only linked share a few items with the group but copy far less than it, like a real account that shared one post: they are not accused.") : null,
      h("div", { class: "scroll" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Account"), h("th", { class: "num" }, "Own content shared with the group"), h("th", null, "Flagged"))),
        h("tbody", null, [...d.accounts.filter(isFlagged), ...d.accounts.filter((a) => !isFlagged(a))].map((a) =>
          h("tr", isFlagged(a) ? null : { class: "linked" },
            h("td", null, a.username, a.thread_only ? h("span", { class: "muted", title: "Every post of this account is in this one thread (no history), so its replies were not counted as evidence." }, " (this thread only)") : null),
            h("td", { class: "num" }, h("span", { class: "share" }, h("span", { class: "share-bar" }, h("span", { style: "width:" + Math.round((a.copied_share || 0) * 100) + "%" })), fmtPct0(a.copied_share))),
            h("td", null, isFlagged(a) ? "yes" : "only linked"))))))),
    h("details", { class: "more" }, h("summary", null, "All linked pairs (" + fmtInt(d.edge_count) + ")"),
      h("div", { class: "scroll" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Account"), h("th", null, "Account"), h("th", null, "Linked by"), h("th", { class: "num" }, "Shared items"))),
        h("tbody", null, shownEdges.map((e) => h("tr", null,
          h("td", null, e.source), h("td", null, e.target), h("td", null, kindName(e.kind)), h("td", { class: "num" }, String(e.shared))))))),
      d.edge_count > shownEdges.length ? h("p", { class: "muted" }, "Showing the " + shownEdges.length + " strongest of " + fmtInt(d.edge_count) + ".") : null,
      h("p", { class: "muted" }, CONF_NOTE + " Active " + fmtTime(d.first_seen) + " to " + fmtTime(d.last_seen) + ".")));
}

function renderItems(items) {
  if (!items.length) return h("p", { class: "muted" }, "No shared items listed.");
  return h("ul", { class: "shared" }, items.map((it) => h("li", null,
    h("span", { class: "shared-kind", title: kindName(it.kind) }, KIND_ICON[it.kind] || "•"),
    h("span", { class: "shared-text" }, it.value || "(empty)"),
    h("span", { class: "shared-meta" }, it.accounts + " accounts" +
      (it.first_seen ? " · " + fmtDay(it.first_seen) : "")))));
}

function renderGraph(accounts, edges, color, linkedOnly) {
  const size = 360, c = size / 2, r = accounts.length > 1 ? 110 : 0;
  const pos = new Map(accounts.map((a, i) => {
    const angle = (2 * Math.PI * i) / accounts.length - Math.PI / 2;
    return [a, { x: c + r * Math.cos(angle), y: c + r * Math.sin(angle), cos: Math.cos(angle), sin: Math.sin(angle) }];
  }));
  const max = Math.max(1, ...edges.map((e) => e.shared));
  const root = svg("svg", { class: "graph", viewBox: "0 0 " + size + " " + size, role: "img",
                            "aria-label": "Graph of linked accounts; thicker lines mean more shared items. The tables have the same data." });
  for (const e of edges) {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (a && b) root.append(svg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, "stroke-width": (1 + 3 * e.shared / max).toFixed(1) }));
  }
  for (const [name, p] of pos) {
    const label = svg("text", { x: p.x + 12 * p.cos, y: p.y + 12 * p.sin + 4,
                                "text-anchor": p.cos > 0.3 ? "start" : p.cos < -0.3 ? "end" : "middle" });
    label.textContent = name.length > 14 ? name.slice(0, 13) + "…" : name;
    root.append(linkedOnly && linkedOnly.has(name)
      ? svg("circle", { class: "linked-dot", cx: p.x, cy: p.y, r: 6 })
      : svg("circle", { cx: p.x, cy: p.y, r: 7, style: color ? "fill:" + color : "" }), label);
  }
  return root;
}

// ---- input: one field; the arrow beside it switches to a saved Reddit page or your own CSV ----

const MODES = ["link", "reddit", "csv"];
let mode = "link";

function setMode(next, focus) {
  mode = next;
  document.querySelectorAll(".omni-pane").forEach((p) => { p.hidden = p.dataset.mode !== next; });
  document.querySelectorAll(".omni-help details").forEach((d) => { d.hidden = d.dataset.for !== next; });
  document.querySelectorAll("#mode-menu button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.mode === next)));
  $("omni").dataset.mode = next;
  closeModeMenu();
  if (focus) {
    const first = document.querySelector('.omni-pane[data-mode="' + next + '"] input');
    if (first) first.focus();
  }
}

function closeModeMenu() {
  $("mode-menu").hidden = true;
  $("mode-toggle").setAttribute("aria-expanded", "false");
}

$("mode-toggle").addEventListener("click", () => {
  const open = $("mode-menu").hidden;
  $("mode-menu").hidden = !open;
  $("mode-toggle").setAttribute("aria-expanded", String(open));
  if (open) $("mode-menu").querySelector('[aria-current="true"]')?.focus();
});
document.querySelectorAll("#mode-menu button").forEach((b, i, all) => {
  b.addEventListener("click", () => setMode(b.dataset.mode, true));
  b.addEventListener("keydown", (e) => {
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (step) { e.preventDefault(); all[(i + step + all.length) % all.length].focus(); }
    if (e.key === "Escape") { closeModeMenu(); $("mode-toggle").focus(); }
  });
});
document.addEventListener("click", (e) => { if (!$("omni").contains(e.target)) closeModeMenu(); });

// Show the chosen file's name on its picker.
document.querySelectorAll(".file-pick input").forEach((input) => {
  const label = input.closest(".file-pick").querySelector("span");
  const original = label.innerHTML;
  input.addEventListener("change", () => {
    if (input.files[0]) label.textContent = input.files[0].name;
    else label.innerHTML = original;
    input.closest(".file-pick").classList.toggle("chosen", !!input.files[0]);
  });
});

setMode("link");

// ---- upload ----

async function analyse(comments, profiles) {
  showError("");
  if (!comments) return showError("Choose a comments CSV file first. The profiles file is optional.");
  const total = comments.size + (profiles ? profiles.size : 0);
  if (comments.size === 0) return showError(comments.name + " is empty.");
  if (total > MAX_BYTES) return showError("The files are too large (limit 20 MB together).");
  const names = comments.name + (profiles ? " and " + profiles.name : "");
  setBusy("Analysing " + names + "…");
  try {
    const form = new FormData();
    form.append("comments", comments, comments.name);
    if (profiles) form.append("profiles", profiles, profiles.name);
    const listing = await api("/api/analyze", { method: "POST", body: form });
    setBusy("");
    if (jobIdFromHash()) history.replaceState(null, "", location.pathname + location.search);
    await showResult(listing, SHARED);
  } catch (e) {
    setBusy("");
    showError(e.status === 404 || e.status === 405
      ? "This server does not accept uploads yet (POST /api/analyze is missing)."
      : "Could not analyse " + names + ": " + e.message);
  }
}

$("upload-form").addEventListener("submit", (e) => {
  e.preventDefault();
  analyse($("comments-file").files[0], $("profiles-file").files[0]);
});

// Dropping CSV files anywhere on the page analyses them; a dropped .html is a saved Reddit page.
for (const type of ["dragenter", "dragover"]) {
  window.addEventListener(type, (e) => { e.preventDefault(); document.body.classList.add("dragging"); });
}
window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) document.body.classList.remove("dragging"); });
window.addEventListener("drop", (e) => {
  e.preventDefault();
  document.body.classList.remove("dragging");
  if ($("analyse").disabled || $("reddit-start").disabled) return;
  const files = [...(e.dataTransfer ? e.dataTransfer.files : [])];
  if (!files.length) return;
  if (files.length === 1 && /\.html?$/i.test(files[0].name)) { setMode("reddit"); return startReddit(files[0]); }
  setMode("csv");
  if (files.length > 2) return showError("Drop at most two files: comments and profiles.");
  const isProfile = (f) => /profile/i.test(f.name);
  let profiles = files.find(isProfile);
  let comments = files.find((f) => f !== profiles);
  if (!comments) { comments = profiles; profiles = undefined; } // a single file is always the comments file
  analyse(comments, profiles);
});

// ---- Discussion analysis: a link or a saved Reddit page (a background job with its own link) ----

const jobIdFromHash = () => (location.hash.match(/job=([\w-]{8,40})/) || [])[1] || null;
let jobCard = "url";   // which status line shows the progress and errors of the running job: "url" or "reddit"

function jobError(message) {
  for (const card of ["url", "reddit"]) {
    const el = $(card + "-error");
    el.textContent = card === jobCard ? message : "";
    el.hidden = !(message && card === jobCard);
  }
}

function jobStatus(...nodes) {
  $("url-status").replaceChildren(...(jobCard === "url" ? nodes : []));
  $("reddit-status").replaceChildren(...(jobCard === "reddit" ? nodes : []));
}

function bannerLines(job) {
  const t = job.thread || {};
  const failed = job.histories_failed ? " (" + job.histories_failed + " could not be fetched)" : "";
  const cost = " in " + job.seconds + " s, " + job.credits_used + " Context.dev credits.";
  if (t.platform === "Bluesky") {
    const via = t.via || {};
    const direct = via.direct || 0, viaContext = via["context.dev"] || 0;
    const how = !direct ? "through Context.dev" : !viaContext ? "directly from Bluesky's public API" :
      "through Context.dev (" + direct + " of " + (direct + viaContext) + " requests directly from Bluesky's public API)";
    const missing = t.comments_expected != null && t.comments_found < t.comments_expected;
    return [h("p", null,
      "Read " + fmtInt(t.comments_found) + " replies from " + fmtInt(t.commenters) + " participants" +
      (t.comments_expected != null ? " (Bluesky reports " + fmtInt(t.comments_expected) + (missing ? "; the rest are deleted, hidden or blocked" : "") + ")" : "") +
      (t.comments_hidden ? "; " + fmtInt(t.comments_hidden) + " replies are blocked or removed" : "") +
      ". Fetched the newest " + t.history_per_commenter + " posts, replies and reposts of " + fmtInt(job.histories_ok) +
      (t.commenters_fetched < t.commenters ? " of " + fmtInt(t.commenters) : "") + " participants" + failed +
      (t.reposts != null ? ", " + fmtInt(t.reposts) + " reposts among them" : "") + ", " + how + cost)];
  }
  if (t.platform !== "Reddit") {
    return [h("p", null,
      "Read " + fmtInt(t.comments_found) + (t.comments_expected != null ? " of " + fmtInt(t.comments_expected) : "") +
      " comments" + (t.commenters != null ? " from " + fmtInt(t.commenters) + " participants" : "") +
      (t.history_per_commenter && (job.histories_ok || job.histories_failed)
        ? ". Fetched the newest " + t.history_per_commenter + " posts of " + fmtInt(job.histories_ok) + " participants" + failed
        : ". One page only: the participants' other posts were not fetched, so only copied text and shared links can link them") +
      cost)];
  }
  const missing = t.comments_expected != null && t.comments_found < t.comments_expected;
  return [h("p", null,
    "Read " + t.comments_found + (t.comments_expected != null ? " of " + t.comments_expected : "") +
    (t.url ? " comments from the thread link" : " comments from the saved page") +
    (missing ? (t.url ? " (the rest are behind “load more”: save the page and use “Saved Reddit page” from the arrow menu to include them)"
                      : " (the rest were behind “load more” when the page was saved)") : "") + ". Fetched the newest " +
    t.history_per_commenter + " comments of " + job.histories_ok + " commenters with Context.dev" + failed + cost)];
}

function renderJobBanner(job) {
  const el = $("job-banner");
  if (!job) { el.replaceChildren(); return; }
  el.replaceChildren(
    h("h3", null, "What was read"),
    ...bannerLines(job),
    h("p", { class: "muted" }, "Private result: only people with this page's link can see it, and it is deleted after 3 hours."));
}

function setJobBusy(busy) {
  for (const id of ["reddit-file", "reddit-start", "url-input", "url-start", "mode-toggle"]) $(id).disabled = busy;
}

async function pollJob(id) {
  const token = ++loadToken;
  showError("");
  jobError("");
  for (;;) {
    let job;
    try {
      job = await api("/api/jobs/" + encodeURIComponent(id));
    } catch (e) {
      if (token !== loadToken) return;
      setJobBusy(false);
      jobStatus();
      return jobError(e.status === 404 ? "This analysis no longer exists: results are deleted after 3 hours." : e.message);
    }
    if (token !== loadToken) return; // the user started something else
    const t = job.thread || {};
    const card = t.platform === "Reddit" && !t.url ? "reddit" : "url";   // a Reddit job from a link has thread.url
    if (card !== jobCard) { jobStatus(); jobCard = card; }
    const p = job.progress || {};
    if (job.status === "collecting" || job.status === "analysing") {
      jobStatus(
        h("span", null, job.stage + (job.status === "collecting" && p.total ? ": " + p.done + " / " + p.total : "") + "…"),
        h("progress", { max: String(p.total || 1), value: String(job.status === "analysing" ? p.total || 1 : p.done || 0) }));
      await new Promise((r) => setTimeout(r, 1500));
      continue;
    }
    setJobBusy(false);
    jobStatus();
    if (job.status === "failed") return jobError("The analysis failed: " + job.error);
    return showResult(job.listing, jobContext(job));
  }
}

async function startJob(card, request, cannot, startingText) {
  jobStatus();
  jobCard = card;
  showError("");
  jobError("");
  setJobBusy(true);
  jobStatus(h("span", null, startingText || "Starting…"));
  try {
    const job = await request();
    history.replaceState(null, "", "#job=" + job.id);
    await pollJob(job.id);
  } catch (e) {
    setJobBusy(false);
    jobStatus();
    jobError(e.status === 404 || e.status === 405 ? cannot : e.message);
  }
}

function startReddit(file) {
  jobCard = "reddit";
  if (!file) return jobError("Choose the saved thread page (.html) first.");
  if (file.size > MAX_PAGE_BYTES) return jobError("The saved page is larger than 100 MB.");
  const form = new FormData();
  form.append("page", file, file.name);
  const mb = file.size / (1024 * 1024);
  return startJob("reddit", () => api("/api/jobs/reddit", { method: "POST", body: form }), "This server cannot analyse Reddit threads yet.",
    mb > 10 ? "Uploading and reading a " + Math.round(mb) + " MB page… up to a couple of minutes." : null);
}

function startUrl(url) {
  jobCard = "url";
  if (!url) return jobError("Paste a link to a post or thread first.");
  return startJob("url", () => api("/api/jobs/url", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }),
    "This server cannot analyse links yet.");
}

$("reddit-form").addEventListener("submit", (e) => {
  e.preventDefault();
  startReddit($("reddit-file").files[0]);
});

$("url-form").addEventListener("submit", (e) => {
  e.preventDefault();
  startUrl($("url-input").value.trim());
});

window.addEventListener("hashchange", () => { const id = jobIdFromHash(); if (id) { setJobBusy(true); pollJob(id); } });

// On page load: a #job= link shows that analysis; otherwise only the start screen (no demo data on open).
if (jobIdFromHash()) { setJobBusy(true); pollJob(jobIdFromHash()); }
