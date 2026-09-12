/* prospect-diagnostic front end. Plain JS, talks to the JSON endpoints, no build step. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = (label, cls) => `<span class="chip ${cls || label}">${esc(String(label).replace(/_/g, " "))}</span>`;
  const STAGES = ["identify", "research", "claims", "verify", "gaps", "report", "human_gate"];
  const STAGE_HINT = { identify: "slug to person", research: "search and fetch", claims: "extract and dedupe", verify: "two passes each", gaps: "three gaps", report: "summary and lint", human_gate: "approve or reject" };

  async function getJSON(url) {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${r.status} ${url}`);
    return r.json();
  }
  async function postForm(url, data) {
    const body = new URLSearchParams(data);
    const r = await fetch(url, { method: "POST", body, headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `${r.status}`);
    return j;
  }
  const when = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) + " UTC" : "");

  /* ---------- index ---------- */
  async function index() {
    const form = $("#runForm");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("#runBtn"), err = $("#runErr");
      err.textContent = "";
      btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Starting';
      try {
        const j = await postForm("/run", { url: $("#url").value.trim() });
        location.href = `/runs/${j.id}`;
      } catch (ex) {
        err.textContent = ex.message; btn.disabled = false; btn.textContent = "Run diagnostic";
      }
    });
    try {
      const runs = await getJSON("/api/runs");
      $("#runCount").textContent = runs.length ? `${runs.length} run${runs.length === 1 ? "" : "s"}` : "";
      $("#runs").innerHTML = runs.length ? runs.map((r) => {
        const c = r.counts || {};
        return `<a class="run-row fade" href="/runs/${esc(r.id)}">
          <div><div class="name">${esc(r.subject || r.input_url)}</div><div class="sub">${esc(r.role || "")}${r.company ? " at " + esc(r.company) : ""}</div></div>
          <div class="sub">${esc(r.id)}</div>
          <div class="counts"><span class="v">${c.verified ?? "-"} ok</span><span class="p">${c.partially_verified ?? "-"} partial</span><span class="r">${c.unverified ?? "-"} refused</span></div>
          ${chip(r.status)}
        </a>`;
      }).join("") : '<div class="empty">No runs yet. Paste a profile URL above.</div>';
    } catch (ex) {
      $("#runs").innerHTML = `<div class="empty">Could not load runs: ${esc(ex.message)}</div>`;
    }
  }

  /* ---------- run detail ---------- */
  let filter = "all";
  function renderRun(d) {
    const s = d.run, L = d.ledger, subj = s.subject || {};
    $("#subject").textContent = subj.full_name || (s.status === "failed" ? "Run failed" : "Identifying subject");
    $("#meta").textContent = [subj.role, subj.company, subj.location].filter(Boolean).join(" · ") + (subj.full_name ? `  ·  confidence ${(subj.confidence || 0).toFixed(2)}` : "") + `  ·  ${when(s.created_at)}`;
    const sc = $("#statusChip"); sc.className = "chip " + s.status; sc.textContent = s.status.replace(/_/g, " ");
    $("#draftLink").hidden = !["draft", "approved", "rejected"].includes(s.status);
    $("#mdLink").hidden = $("#draftLink").hidden;
    $("#runError").textContent = s.error || "";
    // stages
    const cur = STAGES.indexOf(s.stage);
    $("#stages").innerHTML = STAGES.map((st, i) => {
      let cls = "";
      if (s.status === "failed" && i === cur) cls = "failed";
      else if (["draft", "approved", "rejected"].includes(s.status)) cls = "done";
      else if (i < cur) cls = "done";
      else if (i === cur) cls = "active";
      return `<div class="stage ${cls}"><b>${esc(st.replace("_", " "))}</b><span>${esc(STAGE_HINT[st])}</span></div>`;
    }).join("");
    // stats
    const c = s.counts || {};
    const n = (L.findings || []).length;
    $("#stats").innerHTML = `
      <div class="stat"><b>${(L.sources || []).length}</b><span>sources</span></div>
      <div class="stat v"><b>${c.verified ?? 0}</b><span>verified</span></div>
      <div class="stat p"><b>${c.partially_verified ?? 0}</b><span>partially verified</span></div>
      <div class="stat r"><b>${c.unverified ?? 0}</b><span>refused of ${n}</span></div>`;
    // summary
    if (L.summary) { $("#summaryCard").hidden = false; $("#summary").innerHTML = `<p>${esc(L.summary)}</p>`; }
    // gaps
    if ((L.gaps || []).length) {
      $("#gapsCard").hidden = false;
      $("#gaps").innerHTML = L.gaps.map((g, i) => `<div class="gap"><span class="n">${i + 1}</span><b class="t">${esc(g.title)}</b>
        <p>${esc(g.what_is_missing)} ${esc(g.why_it_matters)}</p><p class="fix">Fix: ${esc(g.fix)}</p><div class="ev">Evidence: ${esc((g.evidence || []).join(", "))}</div></div>`).join("");
    }
    // findings
    const F = L.findings || [];
    if (F.length) {
      $("#findingsCard").hidden = false;
      const counts = { all: F.length, verified: 0, partially_verified: 0, unverified: 0 };
      F.forEach((f) => counts[f.label]++);
      $("#tabs").innerHTML = ["all", "verified", "partially_verified", "unverified"].map((k) =>
        `<button class="tab ${filter === k ? "on" : ""}" data-f="${k}">${k === "unverified" ? "refused" : k.replace("_", " ")} · ${counts[k]}</button>`).join("");
      $("#tabs").querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; renderRun(d); }));
      $("#findings").innerHTML = F.filter((f) => filter === "all" || f.label === filter).map((f) => `
        <details class="finding">
          <summary><span class="fid">${esc(f.id)}</span><div><div class="claim">${esc(f.claim)}</div><div class="cat">${esc(f.category)} · ${esc(f.about)} · from ${esc(f.origin_tier)}</div></div>${chip(f.label)}</summary>
          <div class="body">
            <p><b>Why:</b> ${esc(f.reason)}</p>
            ${(f.sources || []).length ? `<p><b>Sources:</b><br>${f.sources.map((u) => `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join("")}</p>` : ""}
            <p><b>First seen:</b> <a class="src" href="${esc(f.origin_url)}" target="_blank" rel="noopener">${esc(f.origin_url)}</a></p>
            ${(f.passes || []).map((p, i) => `<div class="pass"><b>Pass ${i + 1} · ${esc(p.model)} · ${esc(p.verdict)}</b>
              <div>${esc(p.note || "")}${p.discrepancy ? " Discrepancy: " + esc(p.discrepancy) : ""}</div>
              ${(p.cited || []).slice(0, 2).map((c) => `<div class="ex">${esc(c.text)}<br><span class="chip ${esc(c.tier)} plain">${esc(c.tier)}</span> ${esc(c.url)}</div>`).join("")}
            </div>`).join("")}
          </div>
        </details>`).join("") || '<div class="empty">Nothing in this bucket.</div>';
    }
    // sources
    const S = L.sources || [];
    if (S.length) $("#sources").innerHTML = S.map((x) => `<div class="source">${chip(x.tier)}<div><a class="u" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.url)}</a>
      ${x.status === "ok" ? `<div class="hint">${x.chars.toLocaleString()} chars archived</div>` : `<div class="e">could not check: ${esc(x.error || x.status)}</div>`}</div></div>`).join("");
    renderGate(s, L, "run");
  }
  function renderLog(entries) {
    const el = $("#log"); if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    el.innerHTML = entries.map((e) => `<div><span class="t">${esc(e.ts.slice(11, 19))}</span><span class="s">${esc(e.stage)}</span><span>${esc(e.message)}${e.data && e.data.error ? ` <span class="e">${esc(e.data.error)}</span>` : ""}</span></div>`).join("");
    if (atBottom) el.scrollTop = el.scrollHeight;
  }
  function renderGate(s, L, page) {
    const g = $("#gate"); if (!g) return;
    const rid = s.id;
    if (s.status === "approved") {
      g.innerHTML = `<h2>Human gate</h2><div class="ok-banner"><b>Approved</b> by ${esc(s.approval.by)}<br><span class="hint" style="color:inherit">${when(s.approval.at)}</span><p style="margin:8px 0 0">${esc(s.approval.note)}</p></div>`;
    } else if (s.status === "rejected") {
      g.innerHTML = `<h2>Human gate</h2><div class="bad-banner"><b>Rejected</b> by ${esc(s.rejection.by)}<p style="margin:8px 0 0">${esc(s.rejection.note)}</p></div>`;
    } else if (s.status === "draft") {
      const warns = (L && L.lint) || [];
      g.innerHTML = `<h2>Human gate</h2>
        <p class="hint">Read the refused list and open the sources before you sign. Your name and note go into the ledger and the diagnostic header.</p>
        ${warns.length && page === "run" ? `<ul class="warnlist">${warns.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
        ${page === "run" ? `<p><a class="btn" href="/runs/${esc(rid)}/draft">Open the full draft</a></p>` : ""}
        <form id="approveForm"><label class="lbl">Your name</label><input class="text" name="by" required placeholder="Full name">
        <label class="lbl">What did you check?</label><textarea class="text" name="note" rows="3" required placeholder="At least 10 characters"></textarea>
        <div class="err" id="gateErr"></div>
        <div style="display:flex;gap:10px;margin-top:12px"><button class="btn primary" type="submit">Approve</button><button class="btn danger" type="button" id="rejectBtn">Reject</button></div></form>`;
      const form = $("#approveForm");
      const submit = async (action) => {
        const data = Object.fromEntries(new FormData(form).entries());
        $("#gateErr").textContent = "";
        try { await postForm(`/runs/${rid}/${action}`, data); location.reload(); }
        catch (ex) { $("#gateErr").textContent = ex.message; }
      };
      form.addEventListener("submit", (e) => { e.preventDefault(); submit("approve"); });
      $("#rejectBtn").addEventListener("click", () => submit("reject"));
    } else if (s.status === "failed") {
      g.innerHTML = `<h2>Human gate</h2><div class="bad-banner"><b>Run failed</b><p style="margin:8px 0 0">${esc(s.error)}</p></div><p class="hint">Fix the cause and start a new run. Nothing is approved from a failed run.</p>`;
    } else {
      g.innerHTML = `<h2>Human gate</h2><p class="hint"><span class="spin"></span>Waiting for the pipeline to produce a draft.</p>`;
    }
  }
  async function runPage() {
    const app = $("#app"); if (!app || !$("#stages")) return;
    const rid = app.dataset.run;
    async function tick() {
      try {
        const [d, log] = await Promise.all([getJSON(`/runs/${rid}/ledger.json`), getJSON(`/runs/${rid}/log`)]);
        renderRun(d); renderLog(log);
        if (["created", "running"].includes(d.run.status)) setTimeout(tick, 3000);
      } catch (ex) { $("#runError").textContent = ex.message; setTimeout(tick, 5000); }
    }
    tick();
  }

  /* ---------- draft review ---------- */
  function md(text) {
    const lines = text.split("\n"); let out = [], list = null, para = [];
    const flushP = () => { if (para.length) { out.push(`<p>${esc(para.join(" "))}</p>`); para = []; } };
    const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
    for (const raw of lines) {
      const line = raw.replace(/\s+$/, "");
      if (!line.trim()) { flushP(); closeList(); continue; }
      let m;
      if ((m = line.match(/^# (.*)/))) { flushP(); closeList(); out.push(`<h1>${esc(m[1])}</h1>`); }
      else if ((m = line.match(/^## (.*)/))) { flushP(); closeList(); out.push(`<h2>${esc(m[1])}</h2>`); }
      else if ((m = line.match(/^Status: (APPROVED|DRAFT)(.*)/))) { flushP(); closeList(); out.push(`<div class="status ${m[1].toLowerCase()}">${esc(line)}</div>`); }
      else if ((m = line.match(/^- (.*)/))) { flushP(); if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; } out.push(`<li>${esc(m[1])}`); }
      else if ((m = line.match(/^(\d+)\. (.*)/))) { flushP(); if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; } out.push(`<li>${esc(m[2])}`); }
      else if (list && /^\s{2,}/.test(raw)) { out.push(`<span class="cont">${esc(line.trim())}</span>`); }
      else { closeList(); para.push(line); }
    }
    flushP(); closeList();
    return out.join("\n").replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }
  async function draftPage() {
    const app = $("#app"); if (!app || !$("#doc")) return;
    const rid = app.dataset.run;
    try {
      const [d, text] = await Promise.all([getJSON(`/runs/${rid}/ledger.json`), fetch(`/runs/${rid}/diagnostic.md`).then((r) => (r.ok ? r.text() : Promise.reject(new Error("no draft yet"))))]);
      const s = d.run, subj = s.subject || {};
      $("#subject").textContent = subj.full_name || "Diagnostic";
      $("#meta").textContent = [subj.role, subj.company].filter(Boolean).join(", ");
      const sc = $("#statusChip"); sc.className = "chip " + s.status; sc.textContent = s.status;
      $("#doc").innerHTML = md(text);
      const warns = d.ledger.lint || [];
      if (warns.length) { $("#warnCard").hidden = false; $("#warns").innerHTML = warns.map((w) => `<li>${esc(w)}</li>`).join(""); }
      renderGate(s, d.ledger, "draft");
    } catch (ex) { $("#doc").innerHTML = `<div class="empty">${esc(ex.message)}</div>`; }
  }

  index(); runPage(); draftPage();
})();
