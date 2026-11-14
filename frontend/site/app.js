// Dashboard for the API in docs/api.md, plus the proposed POST /api/analyze (CSV upload).
// No build step, no dependencies. All server text goes in through textContent.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || window.SWARM_API_BASE || "").replace(/\/+$/, "");
const MAX_BYTES = 20 * 1024 * 1024; // same limit as the API and nginx
const MAX_TIMELINE = 200;

const $ = (id) => document.getElementById(id);

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child != null) el.append(child);
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
  if (status === 413) return "The file is too large (limit 20 MB).";
  return "The server answered with error " + status + ".";
}

const fmtTime = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
};
const fmtPct = (x) => (x == null ? "n/a" : (x * 100).toFixed(1) + " %");
const fmtInt = (n) => (typeof n === "number" ? n.toLocaleString("en-GB") : "n/a");

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function setBusy(text) {
  $("status").textContent = text || "";
  $("try-sample").disabled = !!text;
  $("file").disabled = !!text;
}

// ---- loading ----

let details = new Map(); // swarm id -> detail object
let loadToken = 0;       // ignore answers that belong to an older dataset

async function showDataset(listing) {
  const token = ++loadToken;
  details = new Map();
  $("results").hidden = false;
  renderSource(listing, null);
  $("flagged").replaceChildren(h("p", { class: "muted" }, "Loading accounts…"));
  $("metrics").replaceChildren(h("p", { class: "muted" }, "Loading…"));
  $("detail").replaceChildren();
  renderSwarmList(listing.swarms);

  api("/api/metrics").then(
    (m) => { if (token === loadToken) renderMetrics(m); },
    (e) => { if (token === loadToken) $("metrics").replaceChildren(h("p", { class: "error" }, e.message)); }
  );

  try {
    const ids = listing.swarms.map((s) => s.id);
    for (let i = 0; i < ids.length; i += 6) { // a few at a time
      const batch = await Promise.all(ids.slice(i, i + 6).map((id) => api("/api/swarms/" + encodeURIComponent(id))));
      if (token !== loadToken) return;
      batch.forEach((d) => details.set(d.id, d));
    }
  } catch (e) {
    if (token !== loadToken) return;
    $("flagged").replaceChildren(h("p", { class: "error" }, e.status === 404
      ? "The data on the server changed while loading (someone else uploaded a file). Reload the page or upload again."
      : e.message));
    return;
  }
  renderSource(listing, countFlagged());
  renderFlagged(listing.swarms);
}

const countFlagged = () => new Set([...details.values()].flatMap((d) => d.accounts)).size;

function renderSource(listing, flagged) {
  const src = listing.source || {};
  const synthetic = src.synthetic === true;
  $("synthetic-badge").hidden = !synthetic;
  $("synthetic-note").hidden = !synthetic;
  const tile = (label, value, small) => h("div", null, h("dt", null, label), h("dd", small ? { class: "small" } : null, value));
  $("summary").replaceChildren(
    tile("Dataset", (src.name || "unknown") + (synthetic ? " (synthetic)" : ""), true),
    tile("Posts", fmtInt(src.posts)),
    tile("Accounts", fmtInt(src.accounts)),
    tile("Swarms found", fmtInt(listing.swarms.length)),
    tile("Flagged accounts", flagged == null ? "…" : fmtInt(flagged))
  );
}

function renderFlagged(swarms) {
  if (!swarms.length) {
    $("flagged").replaceChildren(h("p", null, "No swarms found: no account is flagged in this data."));
    return;
  }
  const all = [];
  const groups = swarms.map((s, i) => {
    const accounts = details.get(s.id).accounts;
    all.push(...accounts);
    return h("div", { class: "group" },
      h("div", { class: "group-head" },
        h("strong", null, "Swarm " + (i + 1) + ": " + accounts.length + " accounts"),
        h("button", { type: "button", onclick: () => selectSwarm(s.id, true) }, "Show evidence")),
      h("ul", { class: "chips" }, accounts.map((a) => h("li", null, a))));
  });
  const copy = h("button", { type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(all.join("\n")); copy.textContent = "Copied"; }
    catch (e) { copy.textContent = "Copy failed"; }
  } }, "Copy all " + all.length + " names");
  $("flagged").replaceChildren(h("p", null, copy), ...groups);
}

function renderMetrics(data) {
  const m = data.metrics;
  if (!m) {
    $("metrics").replaceChildren(h("p", null,
      "No labels in this data, so precision and false-positive rate cannot be measured. " +
      "Add a ", h("code", null, "coordinated"), " column (true/false) to get them."));
    return;
  }
  const tile = (label, value) => h("div", null, h("dt", null, label), h("dd", null, value));
  $("metrics").replaceChildren(
    h("dl", { class: "tiles" },
      tile("Precision", fmtPct(m.precision)),
      tile("Recall", fmtPct(m.recall)),
      tile("False-positive rate", fmtPct(m.false_positive_rate))),
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Counted per account"), h("th", { class: "num" }, "Accounts"))),
      h("tbody", null,
        row("Labelled accounts", m.labelled_accounts),
        row("True positives: coordinated and flagged", m.true_positives),
        row("False positives: innocent but flagged", m.false_positives),
        row("False negatives: coordinated but missed", m.false_negatives),
        row("True negatives: innocent and not flagged", m.true_negatives)))),
    h("p", { class: "muted" },
      "Precision = of the flagged accounts, how many are really coordinated. " +
      "False-positive rate = of the innocent accounts, how many were flagged." +
      (data.source && data.source.synthetic ? " Measured on synthetic data: it shows the code works, not how it does on real traffic." : "")));
}

const row = (label, n) => h("tr", null, h("td", null, label), h("td", { class: "num" }, fmtInt(n)));

function renderSwarmList(swarms) {
  if (!swarms.length) {
    $("swarm-list").replaceChildren(h("p", null, "No swarms found in this data."));
    return;
  }
  $("swarm-list").replaceChildren(...swarms.map((s, i) =>
    h("button", { type: "button", class: "swarm-item", "aria-pressed": "false", "data-id": s.id,
                  onclick: () => selectSwarm(s.id, false) },
      h("strong", null, "Swarm " + (i + 1)),
      " · " + s.size + " accounts · " + s.edge_count + " linked pairs · " + s.post_count + " evidence posts · " + verdictShort(s.verdict),
      h("span", { class: "sample" }, "“" + (s.sample_text || "(no text)") + "”"))));
}

const LABELS = { coordinated: "Coordinated", probably_organic: "Probably organic", unclear: "Unclear" };
const verdictShort = (v) => (v && v.label ? "verdict: " + (LABELS[v.label] || v.label) : "no verdict yet");

async function selectSwarm(id, scroll) {
  document.querySelectorAll(".swarm-item").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  const token = loadToken;
  let d = details.get(id);
  if (!d) {
    $("detail").replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try {
      d = await api("/api/swarms/" + encodeURIComponent(id));
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

function renderDetail(d) {
  const edges = [...(d.edges || [])].sort((a, b) => b.shared - a.shared);
  $("detail").replaceChildren(
    h("h3", null, "Swarm " + d.id + ": " + d.size + " accounts"),
    h("p", { class: "muted" }, "Evidence from " + fmtTime(d.first_seen) + " to " + fmtTime(d.last_seen)),
    h("h3", null, "Verdict"),
    renderVerdict(d.verdict),
    h("h3", null, "Accounts"),
    h("ul", { class: "chips" }, d.accounts.map((a) => h("li", null, a))),
    h("h3", null, "Who posted together with whom"),
    d.accounts.length <= 24 ? renderGraph(d.accounts, edges) : null,
    h("div", { class: "scroll" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Account"), h("th", null, "Account"),
        h("th", { class: "num" }, "Times posted the same content together"))),
      h("tbody", null, edges.map((e) => h("tr", null,
        h("td", null, e.source), h("td", null, e.target), h("td", { class: "num" }, String(e.shared))))))),
    h("h3", null, "Evidence posts, oldest first (" + d.posts.length + ")"),
    renderTimeline(d.posts));
}

function renderVerdict(v) {
  if (!v) {
    return h("div", { class: "verdict pending" },
      "Decision model not connected yet. This swarm was found by the timing and text-reuse rules only; " +
      "nobody has yet weighed innocent explanations such as breaking news, a real campaign or an automated news feed.");
  }
  const list = (title, items) => (Array.isArray(items) && items.length
    ? [h("p", null, h("strong", null, title)), h("ul", null, items.map((x) => h("li", null, String(x))))]
    : []);
  return h("div", { class: "verdict" },
    h("p", null, h("strong", null, LABELS[v.label] || String(v.label || "Unknown")),
      typeof v.confidence === "number" ? " · confidence " + fmtPct(v.confidence) : ""),
    list("Reasons", v.reasons),
    list("Innocent explanations considered", v.innocent_explanations));
}

function renderGraph(accounts, edges) {
  const size = 360, c = size / 2, r = accounts.length > 1 ? 110 : 0;
  const pos = new Map(accounts.map((a, i) => {
    const angle = (2 * Math.PI * i) / accounts.length - Math.PI / 2;
    return [a, { x: c + r * Math.cos(angle), y: c + r * Math.sin(angle), cos: Math.cos(angle), sin: Math.sin(angle) }];
  }));
  const max = Math.max(1, ...edges.map((e) => e.shared));
  const root = svg("svg", { class: "graph", viewBox: "0 0 " + size + " " + size, role: "img",
                            "aria-label": "Graph of linked accounts; thicker lines mean more shared posts. The table below has the same data." });
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

function renderTimeline(posts) {
  const list = h("ul", { class: "timeline" });
  const fill = (limit) => {
    const shown = posts.slice(0, limit);
    const items = [];
    shown.forEach((p, i) => {
      if (i > 0) {
        const gap = (new Date(p.timestamp) - new Date(shown[i - 1].timestamp)) / 1000;
        if (gap > 300) items.push(h("li", { class: "gap" }, fmtGap(gap) + " later"));
      }
      items.push(h("li", null,
        h("div", { class: "meta" }, fmtTime(p.timestamp) + " · ", h("strong", null, p.account)),
        h("div", { class: "text" }, p.text || "(no text)")));
    });
    if (posts.length > limit) {
      items.push(h("li", { class: "gap" },
        h("button", { type: "button", onclick: () => fill(Infinity) }, "Show all " + posts.length + " posts")));
    }
    list.replaceChildren(...items);
  };
  fill(MAX_TIMELINE);
  return list;
}

const fmtGap = (s) => (s >= 7200 ? Math.round(s / 3600) + " h" : Math.round(s / 60) + " min");

// ---- upload ----

async function analyse(file) {
  showError("");
  if (!file) return;
  if (file.size === 0) return showError("The file is empty.");
  if (file.size > MAX_BYTES) return showError("The file is too large (limit 20 MB).");
  setBusy("Analysing " + file.name + "…");
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const listing = await api("/api/analyze", { method: "POST", body: form });
    setBusy("");
    $("status").textContent = "Showing results for " + file.name + ".";
    await showDataset(listing);
  } catch (e) {
    setBusy("");
    showError(e.status === 404 || e.status === 405
      ? "This server does not accept uploads yet (POST /api/analyze is missing). The results below are the server's own data."
      : "Could not analyse " + file.name + ": " + e.message);
  } finally {
    $("file").value = "";
  }
}

$("file").addEventListener("change", (e) => analyse(e.target.files[0]));

const drop = $("drop");
for (const type of ["dragenter", "dragover"]) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add("over"); });
}
for (const type of ["dragleave", "drop"]) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.remove("over"); });
}
drop.addEventListener("drop", (e) => { if (!$("file").disabled) analyse(e.dataTransfer.files[0]); });
// A file dropped beside the box must not make the browser navigate away from the page.
for (const type of ["dragover", "drop"]) window.addEventListener(type, (e) => e.preventDefault());

$("try-sample").addEventListener("click", async () => {
  showError("");
  setBusy("Fetching the synthetic sample…");
  try {
    const response = await fetch("samples/synthetic_sample.csv");
    if (!response.ok) throw new Error("The sample file is missing on this server.");
    const blob = await response.blob();
    setBusy("");
    await analyse(new File([blob], "synthetic_sample.csv", { type: "text/csv" }));
  } catch (e) {
    setBusy("");
    showError(e.message);
  }
});

// On page load: show whatever the server currently holds (the synthetic sample after a restart).
api("/api/swarms").then(showDataset, (e) => showError("Could not load the current results: " + e.message));
