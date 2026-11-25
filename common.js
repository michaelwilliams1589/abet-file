const PAGES = [
  ["index.html", "Overview"],
  ["meetings.html", "Meetings"],
  ["assessment.html", "Assessment"],
  ["self-study.html", "Review"],
  ["log.html", "Log"],
  ["previous.html", "Previous"]
];

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

function data() {
  if (!window.ABET) throw new Error("data.js did not load");
  return window.ABET;
}

function typeBadge(type) {
  const t = (type || "").toLowerCase();
  if (!t || t === "folder") return "";
  return `<span class="badge ${esc(t)}">${esc(t)}</span>`;
}

function statusBadge(status) {
  if (!status) return "";
  const raw = String(status);
  const key = raw.toLowerCase().includes("final") ? "final"
    : raw.toLowerCase().includes("placeholder") ? "placeholder"
    : raw.toLowerCase().includes("open") ? "open"
    : raw.toLowerCase().includes("draft") ? "draft"
    : "";
  return ` <span class="badge ${key}">${esc(raw)}</span>`;
}

function driveLink(url, label, type, cls) {
  if (!url) return `<span class="quiet">${esc(label)} (Drive link not mapped yet)</span>`;
  const klass = cls || "link-chip";
  return `<a class="${klass}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}${type ? " " + typeBadge(type) : ""}</a>`;
}

function fileRow(f, opts) {
  opts = opts || {};
  const label = opts.label || f.name;
  const conf = opts.confidential ? ' <span class="badge confidential">Confidential</span>' : "";
  if (!f.url) {
    return `<div class="item"><span class="file-link">${esc(label)}</span>${conf} ${typeBadge(f.type)}<div class="quiet">Drive link not mapped yet</div></div>`;
  }
  return `<div class="item"><a class="file-link" href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>${conf} ${typeBadge(f.type)}<div class="quiet">Opens in Google Drive</div></div>`;
}

function folderLink(url, label) {
  if (!url) return "";
  return `<a class="folder" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label || "Open folder in Drive")} →</a>`;
}

function nav() {
  const cur = location.pathname.split("/").pop() || "index.html";
  const n = document.createElement("nav");
  n.setAttribute("aria-label", "Main");
  n.innerHTML = PAGES.map(([h, t]) =>
    `<a href="${h}" class="${h === cur ? "on" : ""}">${t}</a>`
  ).join("");
  document.body.appendChild(n);
}

function stamp() {
  try {
    const d = data();
    const el = document.createElement("p");
    el.className = "stamp";
    el.textContent = "Index generated " + (d.generated || "") + " · documents stay in private Google Drive";
    document.body.appendChild(el);
  } catch (_) { /* ignore */ }
}

function meetingCount(d) {
  return (d.years || []).reduce((n, y) => n + (y.meetings || []).length, 0);
}

function renderOverview(root) {
  const d = data();
  const c = d.cycle;
  const meetings = meetingCount(d);
  const recent = (d.log || []).slice().reverse().slice(0, 5);
  root.innerHTML = `
    <div class="stats">
      <div class="stat"><b>Year ${esc(c.year)}</b><span>of ${esc(c.yearsTotal)} · ${esc(c.yearLabel)}</span></div>
      <div class="stat"><b>${meetings}</b><span>Meetings on file</span></div>
      <div class="stat"><b>Y${esc(c.interimYear)}</b><span>Interim ${esc(c.interimLabel)}</span></div>
    </div>

    <h2>Quick links</h2>
    <div class="links">
      ${(d.quickLinks || []).map(l => driveLink(l.url, l.name, l.type, "btn primary")).join("")}
      ${driveLink(c.folderUrl, "Cycle folder", "", "btn")}
      ${driveLink(c.backupUrl, "Backup folder", "", "btn")}
    </div>
    <p class="note" style="margin-top:10px">${folderLink(d.index.folderUrl, "Open the index and log folder")}</p>

    <h2>Open items</h2>
    <ul class="list">
      ${(d.openItems || []).map(i => `<li>${esc(i)}</li>`).join("")}
    </ul>

    <h2>Deadlines</h2>
    <ul class="list">
      ${(d.deadlines || []).map(x =>
        `<li class="deadline"><div class="when">${esc(x.label)}</div><div>${esc(x.text)}</div></li>`
      ).join("")}
    </ul>

    <h2>Recent log entries</h2>
    <div class="log">
      ${recent.map(logCard).join("") || `<p class="empty">No log entries yet.</p>`}
    </div>
    <p><a class="btn" href="log.html">Full running log →</a></p>

    ${d.hubPullRequest ? `
      <h2>Assessment Hub</h2>
      <div class="card">
        <div class="meta">${esc(d.hubPullRequest.status)}</div>
        <a class="btn" href="${esc(d.hubPullRequest.url)}" target="_blank" rel="noopener noreferrer">${esc(d.hubPullRequest.label)}</a>
        <a class="btn" href="assessment.html">Hub files in this cycle →</a>
      </div>` : ""}
  `;
}

function logCard(row) {
  const name = (row.file || "").split("/").pop() || row.file;
  const title = row.url
    ? `<a href="${esc(row.url)}" target="_blank" rel="noopener noreferrer">${esc(name)}</a>`
    : esc(name);
  return `<article class="log-row">
    <div class="top">
      <span class="file">${title}</span>
      <span>${statusBadge(row.status)}</span>
    </div>
    <div class="meta">${esc(row.date)} · ${esc(row.section)} · ${esc(row.year)}</div>
    ${row.notes ? `<div class="summary">${esc(row.notes)}</div>` : ""}
  </article>`;
}

function renderMeetings(root) {
  const d = data();
  root.innerHTML = (d.years || []).map(year => {
    const cards = (year.meetings || []).map(m => {
      const notes = (m.notes || []).map(f => driveLink(f.url, extLabel(f), f.type)).join("");
      const evidence = (m.evidence || []).map(f => driveLink(f.url, f.name, f.type)).join("");
      return `<article class="card">
        <div class="meta">${esc(m.dateLabel || m.date)}${statusBadge(m.status)}</div>
        <h3>${esc(m.title)}</h3>
        ${m.summary ? `<p class="summary">${esc(m.summary)}</p>` : ""}
        <div class="links">${notes}${m.folderUrl ? driveLink(m.folderUrl, "Meeting folder") : ""}</div>
        ${evidence ? `<h3 style="margin-top:12px;font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em">Evidence</h3><div class="links">${evidence}</div>` : ""}
      </article>`;
    }).join("");
    return `<div class="year-head">
        <h2>${esc(year.label)}</h2>
        ${folderLink(year.folderUrl, "Year folder")}
      </div>
      <p class="note">${esc(year.note || "")}</p>
      <div class="cards">${cards || `<p class="empty">No meetings in this year yet.</p>`}</div>`;
  }).join("");
}

function extLabel(f) {
  const t = (f.type || "").toUpperCase();
  if (t === "PDF") return "Notes (PDF)";
  if (t === "DOCX" || t === "DOC") return "Notes (Word)";
  return f.name;
}

function renderAssessment(root) {
  const d = data();
  const a = d.assessment;
  root.innerHTML = `
    <p class="note">${esc(a.note)}</p>
    ${d.hubPullRequest ? `<p class="note"><a class="folder" href="${esc(d.hubPullRequest.url)}" target="_blank" rel="noopener noreferrer">${esc(d.hubPullRequest.label)} — ${esc(d.hubPullRequest.status)} →</a></p>` : ""}
    <div class="year-head"><h2>Latest</h2>${folderLink(a.latestUrl, "Latest folder")}</div>
    <div class="cards">${(a.latest || []).map(f => fileRow(f)).join("") || `<p class="empty">No current hub files yet.</p>`}</div>
    <div class="year-head"><h2>Previous versions</h2>${folderLink(a.previousUrl, "Previous versions")}</div>
    <div class="cards">${(a.previous || []).map(f => fileRow(f)).join("") || `<p class="empty">No superseded hub files yet.</p>`}</div>
  `;
}

function renderSelfStudy(root) {
  const d = data();
  const s = d.selfStudy;
  const o = d.outcomes;
  const inter = s.interim;
  root.innerHTML = `
    <div class="year-head"><h2>Self-study and program review</h2>${folderLink(s.folderUrl, "Open folder")}</div>
    <p class="note">${esc(s.note)}</p>
    ${s.placeholder ? `<p><span class="badge placeholder">Placeholder</span></p>` : ""}
    <div class="cards">${(s.files || []).map(f => fileRow(f)).join("") || `<p class="empty">No self-study files in this cycle yet.</p>`}</div>

    <div class="year-head"><h2>Year 3 interim review (${esc(d.cycle.interimLabel)})</h2>${folderLink(inter.folderUrl, "Open folder")}</div>
    <p class="note">${esc(inter.note)}</p>
    ${inter.placeholder ? `<p><span class="badge placeholder">Placeholder</span></p>` : ""}
    <div class="cards">${(inter.files || []).map(f => fileRow(f)).join("") || `<p class="empty">No interim-review files yet.</p>`}</div>

    <div class="year-head"><h2>Outcomes and HLC</h2>${folderLink(o.folderUrl, "Open folder")}</div>
    <p class="note">${esc(o.note)}</p>
    ${o.placeholder ? `<p><span class="badge placeholder">Placeholder</span></p>` : ""}
    <div class="cards">${(o.files || []).map(f => fileRow(f)).join("") || `<p class="empty">No outcomes or HLC files in this cycle yet.</p>`}</div>
  `;
}

function renderLog(root) {
  const d = data();
  const rows = d.log || [];
  root.innerHTML = `
    <p class="note">Append-only running log for the 2026–2032 cycle. Tap a file name to open it in Google Drive.${folderLink(d.index.folderUrl, " Index folder")}</p>
    <div class="links" style="margin-bottom:12px">
      ${(d.quickLinks || []).filter(l => /log/i.test(l.name)).map(l => driveLink(l.url, l.name, l.type, "btn")).join("")}
    </div>
    <input class="filter" id="log-filter" type="search" placeholder="Filter by file, section, or notes" aria-label="Filter log">
    <div class="log" id="log-list">${rows.map(logCard).join("") || `<p class="empty">No log entries yet.</p>`}</div>
  `;
  const input = document.getElementById("log-filter");
  const list = document.getElementById("log-list");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    const shown = q
      ? rows.filter(r => [r.file, r.section, r.year, r.status, r.notes, r.date].join(" ").toLowerCase().includes(q))
      : rows;
    list.innerHTML = shown.map(logCard).join("") || `<p class="empty">No matching entries.</p>`;
  });
}

function renderPrevious(root) {
  const d = data();
  const p = d.previousCycle;
  const sections = (p.sections || []).map(sec => {
    const conf = new Set(sec.confidential || []);
    const files = (sec.files || []).map(f => fileRow(f, { confidential: conf.has(f.name) })).join("");
    const latest = (sec.latest || []).map(f => fileRow(f)).join("");
    const prev = (sec.previous || []).map(f => fileRow(f)).join("");
    return `<div class="year-head"><h2>${esc(sec.title)}</h2>${folderLink(sec.folderUrl, "Open folder")}</div>
      ${files ? `<div class="cards">${files}</div>` : ""}
      ${latest ? `<p class="note" style="margin-top:10px">${folderLink(sec.latestUrl, "Latest")}</p><div class="cards">${latest}</div>` : ""}
      ${prev ? `<p class="note" style="margin-top:10px">Previous versions ${folderLink(sec.previousUrl, "open folder")}</p><div class="cards">${prev}</div>` : ""}`;
  }).join("");
  root.innerHTML = `
    <p class="note">${esc(p.note)}</p>
    <p>${folderLink(p.folderUrl, "Open the previous-cycle archive")}</p>
    ${sections}
  `;
}

const RENDERERS = {
  "index.html": renderOverview,
  "meetings.html": renderMeetings,
  "assessment.html": renderAssessment,
  "self-study.html": renderSelfStudy,
  "log.html": renderLog,
  "previous.html": renderPrevious
};

function boot() {
  nav();
  const page = location.pathname.split("/").pop() || "index.html";
  const root = document.getElementById("app");
  if (root && RENDERERS[page]) {
    try { RENDERERS[page](root); }
    catch (err) {
      root.innerHTML = `<p class="banner">Couldn't load the file index (${esc(err.message)}).</p>`;
    }
  }
  stamp();
}

document.addEventListener("DOMContentLoaded", boot);

if ("serviceWorker" in navigator) {
  const had = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (had && !reloaded) { reloaded = true; location.reload(); }
  });
  addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").then(r => r.update()).catch(e => console.warn("SW registration failed", e));
  });
}
