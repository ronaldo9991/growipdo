/* ---------- shared: toggle, run lists, counters ---------- */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = (label, cls) => `<span class="chip ${cls || label}">${esc(String(label).replace(/_/g, " "))}</span>`;
  async function getJSON(url) { const r = await fetch(url, { headers: { Accept: "application/json" } }); if (!r.ok) throw new Error(`${r.status} ${url}`); return r.json(); }

  /* approver token: kept in sessionStorage, attached to every gate action, asked for once per tab */
  window.__token = () => { try { return sessionStorage.getItem("approver_token") || ""; } catch (e) { return ""; } };
  window.__gate = { required: false };
  getJSON("/api/gate").then((g) => { window.__gate = g; document.dispatchEvent(new Event("gate-info")); }).catch(() => {});
  window.__tokenField = () => !window.__gate.required ? "" :
    `<label class="lbl">Approver token</label><input class="text" type="password" name="token" value="${esc(window.__token())}" placeholder="Set by APPROVER_TOKEN" required oninput="try{sessionStorage.setItem('approver_token',this.value)}catch(e){}">`;
  window.__gateNote = () => window.__gate.required ? "" : `<p class="hint">No approver token is configured on this deployment, so the gate is open to anyone with the link. Set APPROVER_TOKEN to lock it.</p>`;

  /* radar schedule notice */
  const sch = $("#schedule");
  if (sch) getJSON("/api/radar/schedule").then((x) => {
    sch.textContent = x.enabled ? `Scheduled every ${x.schedule} UTC for ${x.subjects}. Next run ${x.next.replace("T", " ").slice(0, 16)} UTC${x.last_run_id ? `, last scheduled run ${x.last_run_id}` : ""}.`
      : "Not scheduled. Set RADAR_SCHEDULE, for example mon 09:00, to run this every week without a click.";
  }).catch(() => {});

  /* nav pill: mark the active page */
  const track = document.body.dataset.track || "home";
  $$(".topnav a[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === track));

  /* words pull up: split the text, stagger each word, once, when in view (port of WordsPullUp) */
  $$(".pull[data-pull]").forEach((el) => {
    const words = el.dataset.pull.split(" ");
    el.innerHTML = words.map((w, i) => {
      const last = i === words.length - 1;
      const ast = last && el.dataset.asterisk ? '<span class="ast">*</span>' : "";
      return `<span class="w" style="transition-delay:${i * 80}ms;margin-right:${last ? 0 : "0.25em"}">${esc(w)}${ast}</span>`;
    }).join("");
    const on = () => el.classList.add("on");
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { on(); io.disconnect(); } });
      io.observe(el);
    } else on();
  });
  $$(".reveal").forEach((el) => setTimeout(() => el.classList.add("on"), parseInt(el.dataset.delay || "0", 10)));

  /* run lists: every .runs[data-kind] on the page */
  async function renderLists() {
    const els = $$(".runs[data-kind]"); if (!els.length) return;
    const cache = {};
    async function load(kind) {
      if (!cache[kind]) cache[kind] = getJSON(kind === "radar" ? "/api/radar/runs" : "/api/runs").then((rs) => rs.map((r) => ({ ...r, kind })));
      return cache[kind];
    }
    for (const el of els) {
      const kinds = el.dataset.kind === "mixed" ? ["radar", "diagnostic"] : [el.dataset.kind];
      try {
        let rows = (await Promise.all(kinds.map(load))).flat();
        rows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
        const counter = $(`[data-count="${el.dataset.kind}"]`);
        if (counter) counter.textContent = rows.length ? `${rows.length} run${rows.length === 1 ? "" : "s"}` : "";
        el.innerHTML = rows.length ? rows.map((r) => {
          const c = r.counts || {};
          const href = r.kind === "radar" ? `/radar/runs/${esc(r.id)}` : `/runs/${esc(r.id)}`;
          const counts = r.kind === "radar"
            ? `<span class="r">${c.respond_now ?? "-"} respond</span><span class="p">${c.watch ?? "-"} watch</span><span class="a">${c.ambiguous ?? "-"} ambiguous</span>`
            : `<span class="v">${c.verified ?? "-"} ok</span><span class="p">${c.partially_verified ?? "-"} partial</span><span class="r">${c.unverified ?? "-"} refused</span>`;
          const sub = r.kind === "radar" ? "Track A · weekly brief" : "Track B · diagnostic" + (r.role ? " · " + esc(r.role) : "");
          return `<a class="run-row" href="${href}"><div><div class="name">${esc(r.subject || r.input_url)}</div><div class="sub">${sub}</div></div>
            <div class="sub">${esc(r.id)}</div><div class="counts">${counts}</div>${chip(r.status)}</a>`;
        }).join("") : '<div class="empty">No runs yet.</div>';
      } catch (ex) { el.innerHTML = `<div class="empty">Could not load runs: ${esc(ex.message)}</div>`; }
    }
  }
  renderLists();

  /* counters: animate a .stat b from its previous value to the new one */
  window.__animateStats = function (container) {
    $$(".stat b", container).forEach((b) => {
      const target = parseInt(b.textContent, 10); if (isNaN(target)) return;
      const prev = parseInt(b.dataset.v ?? "0", 10);
      b.dataset.v = String(target);
      if (prev === target) return;
      const stat = b.closest(".stat"); stat.classList.remove("bump"); void stat.offsetWidth; stat.classList.add("bump");
      const t0 = performance.now(), dur = 600;
      (function step(t) { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); b.textContent = String(Math.round(prev + (target - prev) * e)); if (k < 1) requestAnimationFrame(step); })(t0);
    });
  };
  /* stage rail: width by index of the current stage */
  window.__rail = function (stagesEl, stages, current, terminal) {
    let rail = $(".rail", stagesEl); if (!rail) { rail = document.createElement("span"); rail.className = "rail"; stagesEl.appendChild(rail); }
    const i = stages.indexOf(current);
    const frac = terminal ? 1 : i < 0 ? 0 : (i + 0.5) / stages.length;
    requestAnimationFrame(() => { rail.style.width = (frac * 100) + "%"; });
  };
})();

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
    if (!data.token && window.__token()) data = { ...data, token: window.__token() };
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
    const statsEl = $("#stats");
    const prevV = [...statsEl.querySelectorAll(".stat b")].map((b) => b.dataset.v);
    statsEl.innerHTML = `
      <div class="stat"><b>${(L.sources || []).length}</b><span>sources</span></div>
      <div class="stat v"><b>${c.verified ?? 0}</b><span>verified</span></div>
      <div class="stat p"><b>${c.partially_verified ?? 0}</b><span>partially verified</span></div>
      <div class="stat r"><b>${c.unverified ?? 0}</b><span>refused of ${n}</span></div>`;
    [...statsEl.querySelectorAll(".stat b")].forEach((b, i) => { if (prevV[i] != null) b.dataset.v = prevV[i]; });
    window.__animateStats(statsEl);
    window.__rail($("#stages"), STAGES, s.stage, ["draft", "approved", "rejected"].includes(s.status));
    // summary
    if (L.summary) { $("#summaryCard").hidden = false; $("#summary").innerHTML = `<p>${esc(L.summary)}</p>`; }
    // gaps
    if ((L.gaps || []).length) {
      $("#gapsCard").hidden = false;
      $("#gaps").innerHTML = L.gaps.map((g, i) => `<div class="gap"><span class="n">${i + 1}</span><b class="t">${esc(g.title)}</b>
        <p>${esc(g.what_is_missing)} ${esc(g.why_it_matters)}</p><p class="fix">Fix: ${esc(g.fix)}</p><div class="ev">Evidence: ${esc((g.evidence || []).join(", "))}</div></div>`).join("");
    }
    // conflicts
    const C = L.conflicts || [];
    $("#conflictsCard").hidden = !C.length;
    if (C.length) $("#conflicts").innerHTML = C.map((c) => `<div class="gap"><b class="t">${esc(c.ids.join(" and "))}</b><p>${esc(c.what)}</p>${c.claims.map((x) => `<p class="hint">${esc(x)}</p>`).join("")}${c.sources.map((u) => `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join("")}</div>`).join("");
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
    const have = el.childElementCount;
    if (have > entries.length) el.innerHTML = "";
    const start = have > entries.length ? 0 : have;
    el.insertAdjacentHTML("beforeend", entries.slice(start).map((e) => `<div><span class="t">${esc(e.ts.slice(11, 19))}</span><span class="s">${esc(e.stage)}</span><span>${esc(e.message)}${e.data && e.data.error ? ` <span class="e">${esc(e.data.error)}</span>` : ""}</span></div>`).join(""));
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
        ${window.__gateNote()}
        <form id="approveForm">${window.__tokenField()}<label class="lbl">Your name</label><input class="text" name="by" required placeholder="Full name">
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
  async function runPage(once) {
    const app = $("#app"); if (!app || !$("#stages") || app.dataset.kind === "radar") return;
    const rid = app.dataset.run;
    async function tick() {
      try {
        const [d, log] = await Promise.all([getJSON(`/runs/${rid}/ledger.json`), getJSON(`/runs/${rid}/log`)]);
        renderRun(d); renderLog(log);
        if (!once && ["created", "running"].includes(d.run.status)) setTimeout(tick, 3000);
      } catch (ex) { $("#runError").textContent = ex.message; if (!once) setTimeout(tick, 5000); }
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
    const app = $("#app"); if (!app || !$("#doc") || app.dataset.kind === "radar") return;
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

  index(); runPage(false); draftPage();
  document.addEventListener("gate-info", () => { runPage(true); draftPage(); });
})();

/* ---------- Track A: radar ---------- */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = (label, cls) => `<span class="chip ${cls || label}">${esc(String(label).replace(/_/g, " "))}</span>`;
  const when = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) + " UTC" : "");
  async function getJSON(url) { const r = await fetch(url, { headers: { Accept: "application/json" } }); if (!r.ok) throw new Error(`${r.status} ${url}`); return r.json(); }
  async function postForm(url, data) {
    if (!data.token && window.__token()) data = { ...data, token: window.__token() };
    const r = await fetch(url, { method: "POST", body: new URLSearchParams(data), headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `${r.status}`); return j;
  }
  const STAGES = ["profile", "collect", "classify", "brief", "human_gate"];
  const HINT = { profile: "who the subjects are", collect: "search, news, snippets", classify: "two readings each", brief: "three minute read", human_gate: "approve, decide, draft" };

  function radarIndex() {
    const form = $("#radarForm"); if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("#radarBtn"), err = $("#radarErr"); err.textContent = ""; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Starting';
      try { const j = await postForm("/radar/run", { subjects: $("#subjects").value.trim() }); location.href = `/radar/runs/${j.id}`; }
      catch (ex) { err.textContent = ex.message; btn.disabled = false; btn.textContent = "Run radar"; }
    });
  }

  let filter = "all";
  function mentionCard(m, L, rid, s) {
    const f = m.final || {}, p1 = m.pass1 || {}, p2 = m.pass2;
    const resp = (L.responses || {})[m.id];
    const ch = m.channel === "linkedin" ? "LinkedIn · snippet only, not fetched" : `${m.channel} · ${m.fetch_status || ""}`;
    let gateHtml = "";
    if (f.ambiguous && s.status !== "failed") {
      gateHtml = `<form class="inline-form decide-form" data-m="${esc(m.id)}">
        <div class="decide"><label class="lbl">About the subject?<select name="about_subject"><option value="yes">Yes, it is ${esc(m.subject)}</option><option value="no">No, a namesake</option></select></label>
        <label class="lbl">Risk<select name="risk"><option value="watch">Watch</option><option value="ignore">Ignore</option><option value="respond_now">Respond now</option></select></label></div>
        <div class="row"><input class="text" name="by" placeholder="Your name" required><input class="text" name="note" placeholder="Why (optional)"></div>
        <div class="row"><button class="btn primary" type="submit">Record my decision</button></div><div class="err"></div></form>`;
    } else if (f.about_subject !== "no" && f.risk === "respond_now") {
      if (!resp) {
        gateHtml = `<form class="inline-form request-form" data-m="${esc(m.id)}"><p class="hint">Gate 1 of 2: nothing has been drafted. Approve drafting and the model writes a draft for your review.</p>
          <div class="row"><input class="text" name="by" placeholder="Your name" required><input class="text" name="note" placeholder="What the reply must get right" required></div>
          <div class="row"><button class="btn primary" type="submit">Approve drafting a reply</button></div><div class="err"></div></form>`;
      } else if (resp.status === "drafting") {
        gateHtml = `<p class="hint"><span class="spin"></span>Drafting approved by ${esc(resp.requested_by)}; the model is writing.</p>`;
      } else if (resp.status === "draft") {
        gateHtml = `<div class="draftbox">${esc(resp.draft)}</div>${(resp.lint || []).length ? `<ul class="warnlist">${resp.lint.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
          <form class="inline-form approve-form" data-m="${esc(m.id)}"><p class="hint">Gate 2 of 2: drafted after ${esc(resp.requested_by)} approved. Edit if you like, then approve or decline. Approved means ready for a person to post; the system never posts.</p>
          <textarea class="text" name="edited" rows="4">${esc(resp.draft)}</textarea>
          <div class="row"><input class="text" name="by" placeholder="Your name" required><input class="text" name="note" placeholder="Note" required></div>
          <div class="row"><button class="btn primary" type="submit">Approve draft</button><button class="btn danger decline" type="button">Decline</button></div><div class="err"></div></form>`;
      } else if (resp.status === "approved") {
        gateHtml = `<div class="ready">Ready for a human to post · approved by ${esc(resp.approved_by)}${resp.edited ? " (edited)" : ""}</div><div class="draftbox">${esc(resp.draft)}</div>`;
      } else if (resp.status === "declined") {
        gateHtml = `<div class="hint">Draft declined by ${esc(resp.declined_by)}: ${esc(resp.decline_note)}</div>`;
      }
    }
    return `<details class="mention" ${f.ambiguous || f.risk === "respond_now" ? "open" : ""}>
      <summary><span class="fid">${esc(m.id)}</span><div><div class="title">${esc(m.title || m.url)}</div><div class="sub">${chip(m.channel)} ${m.seen_before === true ? chip("seen before", "plain") : m.seen_before === false ? chip("new", "plain") : ""} ${m.reach ? chip("reach " + m.reach.bucket, "plain") : ""} <span>${esc(m.publisher)}</span> <span>${esc(m.date || "undated")}</span> <span>${esc(m.subject)}</span></div></div>
      <div class="chips">${f.ambiguous ? chip("ambiguous") : ""}${f.about_subject === "no" ? chip("namesake", "plain") : chip(f.risk || "pending")}${f.sentiment ? chip(f.sentiment, f.sentiment + " plain") : ""}</div></summary>
      <div class="body">
        <p><a class="src" href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.url)}</a></p>
        <p>${esc(m.snippet)}</p>
        <p><b>Decision:</b> ${esc(f.why || "")}</p>
        <div class="pass"><b>Pass 1 · ${esc(p1.model)} · about ${esc(p1.about_subject)} · ${esc(p1.risk)} · ${esc(p1.sentiment)} · confidence ${(p1.confidence ?? 0).toFixed(2)}</b><div>${esc(p1.reason)}</div>${p1.quote ? `<div class="ex">${esc(p1.quote)}</div>` : ""}</div>
        ${p2 ? `<div class="pass"><b>Pass 2 · ${esc(p2.model)} · about ${esc(p2.about_subject)} · ${esc(p2.risk)} · ${esc(p2.sentiment)} · confidence ${(p2.confidence ?? 0).toFixed(2)}</b><div>${esc(p2.reason)}</div>${p2.quote ? `<div class="ex">${esc(p2.quote)}</div>` : ""}</div>` : `<p class="hint">Confident ignore on pass 1, no second reading.</p>`}
        <p class="hint">${esc(ch)}</p>
        ${gateHtml}
      </div></details>`;
  }
  function wireForms(rid, reload) {
    document.querySelectorAll(".decide-form").forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault(); const d = Object.fromEntries(new FormData(f).entries());
      try { await postForm(`/radar/runs/${rid}/mentions/${f.dataset.m}/decide`, d); reload(); } catch (ex) { $(".err", f).textContent = ex.message; }
    }));
    document.querySelectorAll(".request-form").forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault(); const d = Object.fromEntries(new FormData(f).entries()); const b = $("button", f); b.disabled = true; b.innerHTML = '<span class="spin"></span>Drafting';
      try { await postForm(`/radar/runs/${rid}/mentions/${f.dataset.m}/request`, d); reload(); } catch (ex) { $(".err", f).textContent = ex.message; b.disabled = false; b.textContent = "Approve drafting a reply"; }
    }));
    document.querySelectorAll(".approve-form").forEach((f) => {
      f.addEventListener("submit", async (e) => {
        e.preventDefault(); const d = Object.fromEntries(new FormData(f).entries());
        try { await postForm(`/radar/runs/${rid}/mentions/${f.dataset.m}/approve`, d); reload(); } catch (ex) { $(".err", f).textContent = ex.message; }
      });
      $(".decline", f).addEventListener("click", async () => {
        const d = Object.fromEntries(new FormData(f).entries());
        try { await postForm(`/radar/runs/${rid}/mentions/${f.dataset.m}/decline`, d); reload(); } catch (ex) { $(".err", f).textContent = ex.message; }
      });
    });
  }
  function renderGate(s, L, rid, page) {
    const g = $("#gate"); if (!g) return;
    if (s.status === "approved") {
      g.innerHTML = `<h2>Human gate</h2><div class="ok-banner"><b>Brief approved</b> by ${esc(s.approval.by)}<br><span class="hint" style="color:inherit">${when(s.approval.at)}</span><p style="margin:8px 0 0">${esc(s.approval.note)}</p></div>`;
    } else if (s.status === "draft") {
      const amb = (L.mentions || []).filter((m) => m.final && m.final.ambiguous).length;
      g.innerHTML = `<h2>Human gate</h2><p class="hint">Approving circulates the brief as it stands. ${amb ? `<b>${amb} ambiguous item${amb > 1 ? "s are" : " is"} still undecided</b>; you can approve anyway, they stay listed as held.` : "No ambiguous items remain."}</p>
        ${page === "run" ? `<p><a class="btn" href="/radar/runs/${esc(rid)}/brief">Read the full brief</a></p>` : ""}
        ${window.__gateNote()}
        <form id="approveForm">${window.__tokenField()}<label class="lbl">Your name</label><input class="text" name="by" required placeholder="Full name">
        <label class="lbl">What did you check?</label><textarea class="text" name="note" rows="3" required placeholder="At least 10 characters"></textarea>
        <div class="err" id="gateErr"></div><div style="margin-top:12px"><button class="btn primary" type="submit">Approve brief</button></div></form>`;
      $("#approveForm").addEventListener("submit", async (e) => {
        e.preventDefault(); const d = Object.fromEntries(new FormData(e.target).entries());
        try { await postForm(`/radar/runs/${rid}/approve`, d); location.reload(); } catch (ex) { $("#gateErr").textContent = ex.message; }
      });
    } else if (s.status === "failed") {
      g.innerHTML = `<h2>Human gate</h2><div class="bad-banner"><b>Run failed</b><p style="margin:8px 0 0">${esc(s.error)}</p></div>`;
    } else {
      g.innerHTML = `<h2>Human gate</h2><p class="hint"><span class="spin"></span>Waiting for the pipeline to produce a brief.</p>`;
    }
  }
  function renderRadar(d, rid) {
    const s = d.run, L = d.ledger, c = s.counts || {};
    $("#subject").textContent = (L.subjects || []).join(" and ") || "Profiling subjects";
    $("#meta").textContent = `${when(s.created_at)}${L.profile ? "  ·  " + (L.profile.disambiguators || []).slice(0, 3).join(" · ") : ""}`;
    const sc = $("#statusChip"); sc.className = "chip " + s.status; sc.textContent = s.status.replace(/_/g, " ");
    $("#briefLink").hidden = !["draft", "approved"].includes(s.status); $("#mdLink").hidden = $("#briefLink").hidden;
    $("#runError").textContent = s.error || "";
    const cur = STAGES.indexOf(s.stage);
    $("#stages").innerHTML = STAGES.map((st, i) => {
      let cls = ""; if (s.status === "failed" && i === cur) cls = "failed"; else if (["draft", "approved"].includes(s.status)) cls = "done"; else if (i < cur) cls = "done"; else if (i === cur) cls = "active";
      return `<div class="stage ${cls}"><b>${esc(st.replace("_", " "))}</b><span>${esc(HINT[st])}</span></div>`;
    }).join("");
    const statsEl = $("#stats");
    const prevV = [...statsEl.querySelectorAll(".stat b")].map((b) => b.dataset.v);
    statsEl.innerHTML = `<div class="stat"><b>${c.about_subject ?? (L.mentions || []).length}</b><span>mentions about them</span></div>
      <div class="stat r"><b>${c.respond_now ?? 0}</b><span>respond now</span></div><div class="stat p"><b>${c.watch ?? 0}</b><span>watch</span></div>
      <div class="stat a"><b>${c.ambiguous ?? 0}</b><span>ambiguous, held</span></div>`;
    [...statsEl.querySelectorAll(".stat b")].forEach((b, i) => { if (prevV[i] != null) b.dataset.v = prevV[i]; });
    window.__animateStats(statsEl);
    window.__rail($("#stages"), STAGES, s.stage, ["draft", "approved"].includes(s.status));
    if (L.profile) { $("#profileCard").hidden = false; $("#profile").innerHTML = `<p>${esc(L.profile.profile)}</p><p>${(L.profile.disambiguators || []).map((x) => chip(x, "plain")).join(" ")}</p>`; }
    const M = (L.mentions || []).filter((m) => m.final);
    if (M.length) {
      const amb = M.filter((m) => m.final.ambiguous), resp = M.filter((m) => m.final.about_subject !== "no" && m.final.risk === "respond_now" && !m.final.ambiguous);
      $("#ambCard").hidden = !amb.length; $("#ambiguous").innerHTML = amb.map((m) => mentionCard(m, L, rid, s)).join("");
      $("#respondCard").hidden = !resp.length; $("#respond").innerHTML = resp.map((m) => mentionCard(m, L, rid, s)).join("");
      $("#mentionsCard").hidden = false;
      const counts = { all: M.length, respond_now: 0, watch: 0, ignore: 0, namesake: 0 };
      M.forEach((m) => { if (m.final.about_subject === "no") counts.namesake++; else counts[m.final.risk]++; });
      $("#tabs").innerHTML = ["all", "respond_now", "watch", "ignore", "namesake"].map((k) => `<button class="tab ${filter === k ? "on" : ""}" data-f="${k}">${k.replace("_", " ")} · ${counts[k]}</button>`).join("");
      $("#tabs").querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; renderRadar(d, rid); }));
      $("#mentions").innerHTML = M.filter((m) => filter === "all" || (filter === "namesake" ? m.final.about_subject === "no" : m.final.about_subject !== "no" && m.final.risk === filter)).map((m) => mentionCard(m, L, rid, s)).join("") || '<div class="empty">Nothing here.</div>';
      wireForms(rid, () => radarRun(true));
    }
    renderGate(s, L, rid, "run");
  }
  function renderLog(entries) {
    const el = $("#log"); if (!el) return; const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    const have = el.childElementCount; if (have > entries.length) el.innerHTML = "";
    const start = have > entries.length ? 0 : have;
    el.insertAdjacentHTML("beforeend", entries.slice(start).map((e) => `<div><span class="t">${esc(e.ts.slice(11, 19))}</span><span class="s">${esc(e.stage)}</span><span>${esc(e.message)}${e.data && e.data.error ? ` <span class="e">${esc(e.data.error)}</span>` : ""}</span></div>`).join(""));
    if (atBottom) el.scrollTop = el.scrollHeight;
  }
  async function radarRun(once) {
    const app = $("#app"); if (!app || app.dataset.kind !== "radar" || !$("#stages")) return;
    const rid = app.dataset.run;
    async function tick() {
      try {
        const [d, log] = await Promise.all([getJSON(`/radar/runs/${rid}/ledger.json`), getJSON(`/radar/runs/${rid}/log`)]);
        renderRadar(d, rid); renderLog(log);
        const drafting = Object.values(d.ledger.responses || {}).some((r) => r.status === "drafting");
        if (!once && (["created", "running"].includes(d.run.status) || drafting)) setTimeout(tick, 3000);
      } catch (ex) { $("#runError").textContent = ex.message; if (!once) setTimeout(tick, 5000); }
    }
    tick();
  }
  function md(text) {
    const lines = text.split("\n"); let out = [], list = null, para = [];
    const flushP = () => { if (para.length) { out.push(`<p>${esc(para.join(" "))}</p>`); para = []; } };
    const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
    for (const raw of lines) {
      const line = raw.replace(/\s+$/, ""); if (!line.trim()) { flushP(); closeList(); continue; } let m;
      if ((m = line.match(/^# (.*)/))) { flushP(); closeList(); out.push(`<h1>${esc(m[1])}</h1>`); }
      else if ((m = line.match(/^## (.*)/))) { flushP(); closeList(); out.push(`<h2>${esc(m[1])}</h2>`); }
      else if ((m = line.match(/^Status: (APPROVED|DRAFT)(.*)/))) { flushP(); closeList(); out.push(`<div class="status ${m[1].toLowerCase()}">${esc(line)}</div>`); }
      else if ((m = line.match(/^- (.*)/))) { flushP(); if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; } out.push(`<li>${esc(m[1])}`); }
      else if (list && /^\s{2,}/.test(raw)) { out.push(`<span class="cont">${esc(line.trim())}</span>`); }
      else { closeList(); para.push(line); }
    }
    flushP(); closeList();
    return out.join("\n").replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }
  async function radarBrief() {
    const app = $("#app"); if (!app || app.dataset.kind !== "radar" || !$("#doc")) return;
    const rid = app.dataset.run;
    try {
      const [d, text] = await Promise.all([getJSON(`/radar/runs/${rid}/ledger.json`), fetch(`/radar/runs/${rid}/brief.md`).then((r) => (r.ok ? r.text() : Promise.reject(new Error("no brief yet"))))]);
      const s = d.run; $("#subject").textContent = (d.ledger.subjects || []).join(" and "); $("#meta").textContent = when(s.created_at);
      const sc = $("#statusChip"); sc.className = "chip " + s.status; sc.textContent = s.status;
      $("#doc").innerHTML = md(text);
      const warns = d.ledger.lint || []; if (warns.length) { $("#warnCard").hidden = false; $("#warns").innerHTML = warns.map((w) => `<li>${esc(w)}</li>`).join(""); }
      renderGate(s, d.ledger, rid, "brief");
    } catch (ex) { $("#doc").innerHTML = `<div class="empty">${esc(ex.message)}</div>`; }
  }
  radarIndex(); radarRun(false); radarBrief();
  document.addEventListener("gate-info", () => { radarRun(true); radarBrief(); });
})();
