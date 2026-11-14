// Dashboard for the API in docs/api.md, plus POST /api/analyze (upload, frontend/api/app.py).
// No build step, no dependencies. All server text goes in through textContent.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || window.SWARM_API_BASE || "").replace(/\/+$/, "");
const MAX_BYTES = 20 * 1024 * 1024; // both files together; same limit as the API and nginx
const MAX_EDGE_ROWS = 100;

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
const fmtPct = (x) => (x == null ? "n/a" : (x * 100).toFixed(1) + " %");
const fmtInt = (n) => (typeof n === "number" ? n.toLocaleString("en-GB") : "n/a");
const fmtConf = (x) => (typeof x === "number" ? x.toFixed(2) : "n/a");
const KIND = { text: "Same text", link: "Same link", repost: "Reposted the same comment",
               reply: "Replied to the same comment", similar_text: "Nearly the same text",
               created_together: "Created close together (accounts; adds to links above, never links alone)" };
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
  for (const id of ["try-sample", "analyse", "comments-file", "profiles-file"]) $(id).disabled = !!text;
}

function confidenceBar(x) {
  const value = typeof x === "number" ? Math.max(0, Math.min(1, x)) : 0;
  return h("span", { class: "conf", title: "confidence " + fmtConf(x) },
    h("span", { class: "conf-bar" }, h("span", { style: "width:" + (value * 100).toFixed(0) + "%" })),
    h("span", { class: "conf-num" }, fmtConf(x)));
}

// ---- loading ----

let details = new Map(); // swarm id -> detail object
let loadToken = 0;       // ignore answers that belong to an older result

// Where a result's details come from: the shared result, or one discussion job (Bluesky link, Reddit page).
const SHARED = {
  job: null,
  detail: (id) => api("/api/swarms/" + encodeURIComponent(id)),
  explain: (id) => api("/api/swarms/" + encodeURIComponent(id) + "/explain", { method: "POST" }),
  metrics: () => api("/api/metrics"),
};
let ctx = SHARED;

function jobContext(job) {
  const base = "/api/jobs/" + encodeURIComponent(job.id) + "/swarms/";
  return {
    job,
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
  $("results").hidden = false;
  renderJobBanner(ctx.job);
  renderSource(listing, null);
  renderWarnings(listing.warnings || []);
  renderSignals(listing.signals || {}, listing.parameters || {});
  $("flagged").replaceChildren(h("p", { class: "muted" }, "Loading accounts…"));
  $("metrics").replaceChildren(h("p", { class: "muted" }, "Loading…"));
  $("detail").replaceChildren();
  renderSwarmList(listing.swarms);

  ctx.metrics().then(
    (m) => { if (token === loadToken) renderMetrics(m, listing.parameters || {}); },
    (e) => { if (token === loadToken) $("metrics").replaceChildren(h("p", { class: "error" }, e.message)); }
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
  renderSource(listing, countFlagged());
  renderFlagged(listing.swarms, listing.parameters || {});
}

const countFlagged = () => new Set([...details.values()].flatMap((d) => d.accounts.filter(isFlagged).map((a) => a.username))).size;

function renderSource(listing, flagged) {
  const src = listing.source || {};
  const synthetic = src.synthetic === true;
  $("synthetic-badge").hidden = !synthetic;
  $("synthetic-note").hidden = !synthetic;
  const files = [src.comments_file, src.profiles_file].filter(Boolean).join(" + ") || "unknown";
  const tile = (label, value, small) => h("div", null, h("dt", null, label), h("dd", small ? { class: "small" } : null, value));
  $("summary").replaceChildren(
    tile("Data", files + (synthetic ? " (synthetic)" : ""), true),
    tile("Comments", fmtInt(src.comments)),
    tile("Accounts", fmtInt(src.accounts)),
    tile("Swarms found", fmtInt(listing.swarms.length)),
    tile("Flagged accounts", flagged == null ? "…" : fmtInt(flagged))
  );
}

function renderWarnings(warnings) {
  $("warnings").replaceChildren(...(warnings.length
    ? [h("details", { class: "warnings" },
        h("summary", null, warnings.length + (warnings.length === 1 ? " note" : " notes") + " about the input"),
        h("ul", null, warnings.map((w) => h("li", null, String(w)))))]
    : []));
}

function renderSignals(signals, params) {
  const rows = Object.entries(signals).map(([kind, s]) => h("tr", null,
    h("td", null, kindName(kind)),
    h("td", null, s.status === "used" ? "used" : h("span", { class: "muted" }, "skipped: " + (s.reason || ""))),
    h("td", { class: "num" }, fmtInt(s.items)),
    h("td", { class: "num" }, fmtInt(s.links))));
  $("signals").replaceChildren(
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

function renderFlagged(swarms, params) {
  if (!swarms.length) {
    $("flagged").replaceChildren(h("p", null,
      "No group of accounts reached confidence " + (params.min_confidence ?? "") + " in this data, so no account is flagged. " +
      "With few comments the chance test rarely links anyone; that is on purpose."));
    return;
  }
  const all = [];
  const groups = swarms.map((s, i) => {
    const members = details.get(s.id).accounts;
    const accounts = members.filter(isFlagged);
    const linked = members.length - accounts.length;
    all.push(...accounts.map((a) => a.username));
    return h("div", { class: "group" },
      h("div", { class: "group-head" },
        h("strong", null, "Swarm " + (i + 1) + ": " + accounts.length + " flagged" + (linked ? " of " + members.length + " accounts" : " accounts")),
        confidenceBar(s.confidence),
        h("button", { type: "button", onclick: () => selectSwarm(s.id, true) }, "Show evidence")),
      h("ul", { class: "chips" }, accounts.map((a) =>
        h("li", { title: "shares " + fmtPct(a.copied_share) + " of its own content with this group" }, a.username))),
      linked ? h("p", { class: "muted" }, linked + (linked === 1 ? " more account is" : " more accounts are") +
        " linked to this group but copy far less than it; they are not flagged (see the evidence).") : null);
  });
  const copy = h("button", { type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(all.join("\n")); copy.textContent = "Copied"; }
    catch (e) { copy.textContent = "Copy failed"; }
  } }, "Copy all " + all.length + " names");
  $("flagged").replaceChildren(h("p", null, copy), ...groups);
}

function renderMetrics(data, params) {
  const m = data.metrics;
  if (!m) {
    $("metrics").replaceChildren(h("p", null,
      "No labels in this data, so precision and false-positive rate cannot be measured. " +
      "Upload a profiles file with a ", h("code", null, "label"), " column (human / bot) to get them."));
    return;
  }
  const at = m.at_min_confidence || {};
  const tile = (label, value) => h("div", null, h("dt", null, label), h("dd", null, value));
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
    h("p", { class: "muted" }, "At the shown cut, confidence ≥ " + at.min_confidence + ". Counted per account."),
    h("dl", { class: "tiles" },
      tile("Precision", fmtPct(at.precision)),
      tile("Recall", fmtPct(at.recall)),
      tile("False-positive rate", fmtPct(at.false_positive_rate)),
      tile("Innocent but flagged", fmtInt(at.false_positives))),
    h("p", { class: "note-plain" },
      "Honesty note: the cut " + at.min_confidence + " is the one value chosen with the labels visible, so these numbers are " +
      "somewhat optimistic. Labels are only used to measure; detection never sees them." +
      (data.source && data.source.synthetic ? " Measured on synthetic data: it shows the code works, not how it does on real traffic." : "")),
    h("h3", null, "At other cuts"),
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Confidence"), h("th", { class: "num" }, "Precision"),
        h("th", { class: "num" }, "Recall"), h("th", { class: "num" }, "False-positive rate"),
        h("th", { class: "num" }, "Innocent flagged"))),
      h("tbody", null, thresholds))),
    labels.length ? h("h3", null, "By label") : null,
    labels.length ? h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Label"), h("th", { class: "num" }, "Accounts"),
        h("th", { class: "num" }, "Flagged"), h("th", { class: "num" }, "Share flagged"))),
      h("tbody", null, labels))) : null,
    h("p", { class: "muted" },
      "Precision = of the flagged accounts, how many are labelled bots. Recall = of the bots, how many were flagged. " +
      "False-positive rate = of the accounts not labelled bot, how many were flagged." +
      (m.labelled_without_content ? " " + fmtInt(m.labelled_without_content) + " labelled accounts had no usable content and are left out." : "")));
}

function renderSwarmList(swarms) {
  if (!swarms.length) {
    $("swarm-list").replaceChildren(h("p", null, "No swarms found in this data."));
    return;
  }
  $("swarm-list").replaceChildren(...swarms.map((s, i) =>
    h("button", { type: "button", class: "swarm-item", "aria-pressed": "false", "data-id": s.id,
                  onclick: () => selectSwarm(s.id, false) },
      h("span", { class: "swarm-head" },
        h("strong", null, "Swarm " + (i + 1)),
        h("span", null, (s.flagged_members != null && s.flagged_members < s.size ? s.flagged_members + " flagged of " : "") +
          s.size + " accounts · " + fmtInt(s.edge_count) + " linked pairs"),
        confidenceBar(s.confidence)),
      s.sample ? h("span", { class: "sample" }, kindName(s.sample.kind) + ", " + s.sample.accounts + " accounts: “" + s.sample.value + "”") : null,
      s.declared_automation ? h("span", { class: "sample" }, automationNote(s.declared_automation)) : null)));
}

// docs/api.md: a description, never a verdict; the cluster is never hidden or greyed out for it.
const automationNote = (a) => a.accounts + " of " + a.of + " accounts say they are automated (a feed, or a swarm posing as one): check the source.";

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
  if (scroll) $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- AI explanation of one swarm (Gemini, server side; explain.py). It explains the evidence, it never decides. ----

const explained = new Map(); // swarm id -> explanation answer, for this result

const PLAUS = { low: "unlikely", medium: "possible", high: "likely" };

function renderExplanation(box, answer) {
  const e = answer.explanation || {};
  const refs = (ids) => (ids && ids.length ? h("span", { class: "refs" }, " [" + ids.join(", ") + "]") : null);
  box.className = "verdict explained";
  box.replaceChildren(
    h("p", { class: "ai-label" }, "AI-written explanation of the evidence below, by " + answer.model + ". " +
      "It can be wrong, and it does not change the result." + (answer.note ? " (" + answer.note + ")" : "")),
    h("p", null, h("strong", null, "What the group appears to do: "), e.likely_activity || "unclear"),
    h("p", null, e.summary || ""),
    (e.observations || []).length ? h("ul", null, e.observations.map((o) => h("li", null, o.point, refs(o.evidence)))) : null,
    (e.innocent_explanations || []).length ? h("div", null,
      h("p", null, h("strong", null, "Innocent explanations weighed")),
      h("ul", null, e.innocent_explanations.map((x) => h("li", null,
        h("span", { class: "pill plaus-" + x.plausibility }, PLAUS[x.plausibility] || x.plausibility), " ", x.explanation + ". ",
        h("span", { class: "muted" }, x.why))))) : null,
    (e.what_to_check_next || []).length ? h("div", null,
      h("p", null, h("strong", null, "What to check next")),
      h("ul", null, e.what_to_check_next.map((x) => h("li", null, x)))) : null,
    e.uncertainty ? h("p", { class: "muted" }, h("strong", null, "What the evidence cannot show: "), e.uncertainty) : null,
    renderNews(answer.news || []),
    h("details", null, h("summary", null, "Evidence sent to the model (usernames replaced)"),
      h("pre", null, answer.evidence_sent || "")));
}

// News check (Context.dev news search, server side): coverage of the most shared items while the group was active.
function renderNews(news) {
  if (!news.length) return null;
  let n = 0;
  return h("div", { class: "news" },
    h("p", null, h("strong", null, "News check"), h("span", { class: "muted" },
      " (Context.dev news search for the most shared items, while the group was active ±2 days. Search hits, not confirmed matches.)")),
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
  const box = h("div", { class: "verdict pending" });
  if (explained.has(d.id)) { renderExplanation(box, explained.get(d.id)); return box; }
  const button = h("button", { type: "button", class: "primary" }, "Explain this swarm with AI");
  const say = h("span", { class: "muted" });
  button.addEventListener("click", async () => {
    button.disabled = true;
    say.textContent = " Checking the news and asking the language model… about 15–30 s.";
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
  box.replaceChildren(
    h("p", null, "Before acting, rule out the innocent look-alikes: breaking news, a real campaign, an automated news feed, " +
      "one viral post. A language model can read the evidence below and describe what the group appears to do, " +
      "with the innocent explanations weighed. Usernames are replaced before anything is sent."),
    h("p", null, button, say));
  return box;
}

function renderDetail(d) {
  const edges = [...(d.edges || [])].sort((a, b) => b.shared - a.shared);
  const names = d.accounts.map((a) => a.username);
  const created = d.created_within_30_days;
  const shownEdges = edges.slice(0, MAX_EDGE_ROWS);
  $("detail").replaceChildren(
    h("h3", null, "Swarm " + d.id + ": " + d.size + " accounts"),
    h("p", null, "Confidence ", confidenceBar(d.confidence)),
    h("p", { class: "muted" }, "Active from " + fmtTime(d.first_seen) + " to " + fmtTime(d.last_seen) + "."),
    created ? h("p", null, h("span", { class: "pill" },
      created.accounts + " of " + created.of + " accounts were created within one 30-day window"),
      h("span", { class: "muted" }, " Supporting evidence only; it does not change the confidence.")) : null,
    d.copy_gap_seconds ? h("p", null, h("span", { class: "pill" },
      "Copies follow each other after " + fmtGapSeconds(d.copy_gap_seconds.median) + " (median, over " + fmtInt(d.copy_gap_seconds.items) + " shared items)"),
      h("span", { class: "muted" }, d.copy_gap_seconds.median < 60 ? " Within seconds: typical of automation or a scheduled campaign." : " Evidence only.")) : null,
    d.declared_automation ? h("p", null, h("span", { class: "pill" }, automationNote(d.declared_automation))) : null,
    renderExplainBox(d),
    h("h3", null, "What they share most"),
    renderItems(d.top_items || []),
    h("h3", null, "Members"),
    memberNote(d),
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Account"), h("th", { class: "num" }, "Own content shared with the group"),
        h("th", null, "Flagged"))),
      h("tbody", null, [...d.accounts.filter(isFlagged), ...d.accounts.filter((a) => !isFlagged(a))].map((a) =>
        h("tr", isFlagged(a) ? null : { class: "linked" },
          h("td", null, a.username), h("td", { class: "num" }, fmtPct(a.copied_share)),
          h("td", null, isFlagged(a) ? "yes" : "no, only linked")))))),
    h("h3", null, "Who is linked to whom"),
    names.length <= 24 ? renderGraph(names, edges) : h("p", { class: "muted" }, "Too many accounts for the picture; see the table."),
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Account"), h("th", null, "Account"), h("th", null, "Linked by"),
        h("th", { class: "num" }, "Shared items"))),
      h("tbody", null, shownEdges.map((e) => h("tr", null,
        h("td", null, e.source), h("td", null, e.target), h("td", null, kindName(e.kind)),
        h("td", { class: "num" }, String(e.shared))))))),
    d.edge_count > shownEdges.length
      ? h("p", { class: "muted" }, "Showing the " + shownEdges.length + " strongest of " + fmtInt(d.edge_count) + " linked pairs.")
      : null);
}

function memberNote(d) {
  const flagged = d.accounts.filter(isFlagged).length, linked = d.accounts.length - flagged;
  if (!linked) return null;
  return h("p", { class: "muted" }, flagged + " of " + d.accounts.length + " members are flagged. The other " + linked +
    " are linked to the group by a few shared items but copy far less than it (their own copied share is under half the group's confidence), like a real account that shared one of its posts: they are not accused.");
}

function renderItems(items) {
  if (!items.length) return h("p", { class: "muted" }, "No shared items listed.");
  return h("ul", { class: "timeline" }, items.map((it) => h("li", null,
    h("div", { class: "meta" }, kindName(it.kind) + " · " + it.accounts + " accounts · " +
      (it.first_seen ? fmtTime(it.first_seen) + (it.last_seen && it.last_seen !== it.first_seen ? " – " + fmtTime(it.last_seen) : "") : "no times")),
    h("div", { class: "text" }, it.value || "(empty)"))));
}

function renderGraph(accounts, edges) {
  const size = 360, c = size / 2, r = accounts.length > 1 ? 110 : 0;
  const pos = new Map(accounts.map((a, i) => {
    const angle = (2 * Math.PI * i) / accounts.length - Math.PI / 2;
    return [a, { x: c + r * Math.cos(angle), y: c + r * Math.sin(angle), cos: Math.cos(angle), sin: Math.sin(angle) }];
  }));
  const max = Math.max(1, ...edges.map((e) => e.shared));
  const root = svg("svg", { class: "graph", viewBox: "0 0 " + size + " " + size, role: "img",
                            "aria-label": "Graph of linked accounts; thicker lines mean more shared items. The table below has the same data." });
  for (const e of edges) {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (a && b) root.append(svg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, "stroke-width": (1 + 3 * e.shared / max).toFixed(1) }));
  }
  for (const [name, p] of pos) {
    const label = svg("text", { x: p.x + 12 * p.cos, y: p.y + 12 * p.sin + 4,
                                "text-anchor": p.cos > 0.3 ? "start" : p.cos < -0.3 ? "end" : "middle" });
    label.textContent = name.length > 14 ? name.slice(0, 13) + "…" : name;
    root.append(svg("circle", { cx: p.x, cy: p.y, r: 6 }), label);
  }
  return root;
}

// ---- upload ----

async function analyse(comments, profiles) {
  showError("");
  if (!comments) return showError("Choose a comments CSV file first. The profiles file is optional.");
  const total = comments.size + (profiles ? profiles.size : 0);
  if (comments.size === 0) return showError(comments.name + " is empty.");
  if (total > MAX_BYTES) return showError("The files are too large (limit 20 MB together).");
  const names = comments.name + (profiles ? " and " + profiles.name : "");
  setBusy("Analysing " + names + "… this can take a little while for large files.");
  try {
    const form = new FormData();
    form.append("comments", comments, comments.name);
    if (profiles) form.append("profiles", profiles, profiles.name);
    const listing = await api("/api/analyze", { method: "POST", body: form });
    setBusy("");
    $("status").textContent = "Showing results for " + names + ".";
    if (jobIdFromHash()) history.replaceState(null, "", location.pathname + location.search);
    await showResult(listing, SHARED);
  } catch (e) {
    setBusy("");
    showError(e.status === 404 || e.status === 405
      ? "This server does not accept uploads yet (POST /api/analyze is missing). The results below are the server's own data."
      : "Could not analyse " + names + ": " + e.message);
  }
}

$("upload-form").addEventListener("submit", (e) => {
  e.preventDefault();
  analyse($("comments-file").files[0], $("profiles-file").files[0]);
});

const drop = $("upload-form");
for (const type of ["dragenter", "dragover"]) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add("over"); });
}
for (const type of ["dragleave", "drop"]) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.remove("over"); });
}
drop.addEventListener("drop", (e) => {
  if ($("analyse").disabled) return;
  const files = [...e.dataTransfer.files];
  if (!files.length) return;
  if (files.length > 2) return showError("Drop at most two files: comments and profiles.");
  const isProfile = (f) => /profile/i.test(f.name);
  let profiles = files.find(isProfile);
  let comments = files.find((f) => f !== profiles);
  if (!comments) { comments = profiles; profiles = undefined; } // a single file is always the comments file
  analyse(comments, profiles);
});
// A file dropped beside the box must not make the browser navigate away from the page.
for (const type of ["dragover", "drop"]) window.addEventListener(type, (e) => e.preventDefault());

$("try-sample").addEventListener("click", async () => {
  showError("");
  setBusy("Fetching the synthetic sample…");
  try {
    const get = async (name) => {
      const response = await fetch("samples/" + name);
      if (!response.ok) throw new Error("The sample file " + name + " is missing on this server.");
      return new File([await response.blob()], name, { type: "text/csv" });
    };
    const [comments, profiles] = await Promise.all([get("synthetic_comments.csv"), get("synthetic_profiles.csv")]);
    setBusy("");
    await analyse(comments, profiles);
  } catch (e) {
    setBusy("");
    showError(e.message);
  }
});

// ---- Discussion analysis: a Bluesky link or a saved Reddit page (a background job with its own link) ----

const jobIdFromHash = () => (location.hash.match(/job=([\w-]{8,40})/) || [])[1] || null;
let jobCard = "url";   // which card shows the progress and errors of the running job: "url" or "reddit"

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
    return [
      h("p", null, h("strong", null, "Bluesky thread by @" + (t.author || "?") + ": "), "“" + (t.title || "") + "”"),
      h("p", { class: "muted" },
        "Read " + fmtInt(t.comments_found) + " replies from " + fmtInt(t.commenters) + " participants" +
        (t.comments_expected != null ? " (Bluesky reports " + fmtInt(t.comments_expected) + (missing ? "; the rest are deleted, hidden or blocked" : "") + ")" : "") +
        (t.comments_hidden ? "; " + fmtInt(t.comments_hidden) + " replies are blocked or removed" : "") +
        ". Fetched the newest " + t.history_per_commenter + " posts, replies and reposts of " + fmtInt(job.histories_ok) +
        (t.commenters_fetched < t.commenters ? " of " + fmtInt(t.commenters) : "") + " participants" + failed +
        (t.reposts != null ? ", " + fmtInt(t.reposts) + " reposts among them" : "") + ", " + how + cost),
    ];
  }
  if (t.platform !== "Reddit") {
    return [
      h("p", null, h("strong", null, (t.platform || "Discussion") + ": "), t.title ? "“" + t.title + "”" : (t.url || "")),
      h("p", { class: "muted" },
        "Read " + fmtInt(t.comments_found) + (t.comments_expected != null ? " of " + fmtInt(t.comments_expected) : "") +
        " comments" + (t.commenters != null ? " from " + fmtInt(t.commenters) + " participants" : "") +
        (t.history_per_commenter ? ". Fetched the newest " + t.history_per_commenter + " posts of " + fmtInt(job.histories_ok) + " participants" + failed : "") +
        cost),
    ];
  }
  const missing = t.comments_expected != null && t.comments_found < t.comments_expected;
  return [
    h("p", null, h("strong", null, "Reddit thread: "), (t.subreddit || "") + " · “" + (t.title || "") + "”"),
    h("p", { class: "muted" },
      "Read " + t.comments_found + (t.comments_expected != null ? " of " + t.comments_expected : "") +
      (t.url ? " comments from the thread link" : " comments from the saved page") +
      (missing ? (t.url ? " (the rest are behind “load more”: save the page after loading more to include them)"
                        : " (the rest were behind “load more” when the page was saved)") : "") + ". Fetched the newest " +
      t.history_per_commenter + " comments of " + job.histories_ok + " commenters with Context.dev" + failed + cost),
  ];
}

function renderJobBanner(job) {
  const el = $("job-banner");
  if (!job) { el.hidden = true; el.replaceChildren(); return; }
  el.hidden = false;
  el.replaceChildren(
    ...bannerLines(job),
    h("p", { class: "note-plain" },
      "Private result: only people with this link can see it, and it is deleted after 3 hours. " +
      "A swarm here is a lead to check, not proof: real people who campaign together look the same as a bot network."),
    h("p", null, h("button", { type: "button", onclick: () => { location.hash = ""; loadShared(); } }, "Back to the shared demo")));
}

function setJobBusy(busy) {
  for (const id of ["reddit-file", "reddit-start", "url-input", "url-start"]) $(id).disabled = busy;
}

async function pollJob(id) {
  const token = ++loadToken;
  $("results").hidden = true;
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

async function startJob(card, request, cannot) {
  jobStatus();
  jobCard = card;
  showError("");
  jobError("");
  setJobBusy(true);
  jobStatus(h("span", null, "Starting…"));
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
  if (file.size > 15 * 1024 * 1024) return jobError("The saved page is larger than 15 MB.");
  const form = new FormData();
  form.append("page", file, file.name);
  return startJob("reddit", () => api("/api/jobs/reddit", { method: "POST", body: form }), "This server cannot analyse Reddit threads yet.")
    .finally(() => { $("reddit-file").value = ""; });
}

function startUrl(url) {
  jobCard = "url";
  if (!url) return jobError("Paste the link of a Bluesky post first.");
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

function loadShared() {
  api("/api/swarms").then((l) => showResult(l, SHARED), (e) => showError("Could not load the current results: " + e.message));
}

window.addEventListener("hashchange", () => { const id = jobIdFromHash(); if (id) { setJobBusy(true); pollJob(id); } });

// On page load: a #job= link shows that analysis; otherwise the shared result (the synthetic sample after a restart).
if (jobIdFromHash()) { setJobBusy(true); pollJob(jobIdFromHash()); } else { loadShared(); }
