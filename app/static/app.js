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
  getJSON("/api/gate").then((g) => { window.__gate = { required: !!g.token_required }; document.dispatchEvent(new Event("gate-info")); }).catch(() => {});
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

  /* ---------- usability helpers shared by both tracks ---------- */
  const ux = window.__ux = {};
  ux.shortUrl = (u) => {
    try {
      const x = new URL(u); const host = x.hostname.replace(/^www\./, "");
      let path = decodeURIComponent(x.pathname).replace(/\/$/, "");
      if (path.length > 34) { const parts = path.split("/").filter(Boolean); const last = parts[parts.length - 1] || ""; path = "/…/" + (last.length > 28 ? last.slice(0, 27) + "…" : last); }
      return host + path;
    } catch (e) { return String(u || "").slice(0, 60); }
  };
  ux.link = (u) => `<a class="src" href="${esc(u)}" title="${esc(u)}" target="_blank" rel="noopener">${esc(ux.shortUrl(u))}</a>`;
  ux.ago = (iso) => {
    if (!iso) return ""; const sec = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    if (sec < 60) return "just now"; const m = Math.floor(sec / 60); if (m < 60) return `${m} min ago`;
    const h = Math.floor(m / 60); if (h < 24) return `${h} h ago`; const d = Math.floor(h / 24); return d === 1 ? "yesterday" : `${d} days ago`;
  };
  ux.clock = (iso) => { const t = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
  setInterval(() => $$("[data-since]").forEach((el) => { el.textContent = ux.clock(el.dataset.since); }), 1000);
  ux.EXPECT = { diagnostic: "about 6 minutes", radar: "about 2 minutes" };
  ux.bar = (cfg) => {
    let el = $("#actionbar");
    if (!cfg) { if (el) el.hidden = true; document.body.classList.remove("has-bar"); return; }
    if (!el) { el = document.createElement("div"); el.id = "actionbar"; el.className = "actionbar"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.hidden = false; document.body.classList.add("has-bar");
    const act = cfg.action ? (cfg.action.href ? `<a class="btn primary" href="${esc(cfg.action.href)}">${esc(cfg.action.label)}</a>` : `<button type="button" class="btn primary" id="abBtn">${esc(cfg.action.label)}</button>`) : "";
    el.innerHTML = `<div class="ab-text"><b>${cfg.spin ? '<span class="spin"></span>' : ""}${esc(cfg.title)}</b>${cfg.sub ? `<span>${cfg.sub}</span>` : ""}</div>${act}`;
    if (cfg.action && cfg.action.onClick) $("#abBtn").addEventListener("click", cfg.action.onClick);
  };
  ux.jump = (sel) => {
    /* On touch screens nothing is focused: the browser would scroll the control into view on its own and a
       phone would open the keyboard over the buttons. With a mouse, focus first, then scroll. */
    const t = $(sel); if (!t) return;
    const f = t.querySelector("input:not([type=hidden]),select,textarea");
    if (f && matchMedia("(pointer: fine)").matches) f.focus({ preventScroll: true });
    const top = Math.max(0, t.getBoundingClientRect().top + window.scrollY - 84);
    window.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    /* Some browsers skip or stall smooth scrolling (background tabs, battery saver). Never leave the button doing nothing. */
    setTimeout(() => { if (Math.abs(window.scrollY - top) > 4) window.scrollTo(0, top); }, 1200);
  };
  ux.title = (state, who, trackName) => {
    const map = { created: "Starting", running: "Running", draft: "Needs review", approved: "Approved", rejected: "Rejected", failed: "Failed" };
    document.title = `${map[state] || state} · ${who || "Run"} · ${trackName}`;
  };
  ux.rerun = async (kind, input) => {
    const r = await fetch(kind === "radar" ? "/radar/run" : "/run", { method: "POST", body: new URLSearchParams(kind === "radar" ? { subjects: input } : { url: input }), headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || String(r.status));
    location.href = kind === "radar" ? `/radar/runs/${j.id}` : `/runs/${j.id}`;
  };
  ux.running = (s) => ["created", "running"].includes(s.status);
  ux.progress = (el, s, stages, hints, kind) => {
    if (!el) return;
    if (ux.running(s)) {
      const i = stages.indexOf(s.stage);
      el.innerHTML = `<b><span class="spin"></span>Step ${Math.max(1, i + 1)} of ${stages.length}: ${esc(hints[s.stage] || "starting")}</b><span>Running for <span data-since="${esc(s.created_at)}">${ux.clock(s.created_at)}</span>. Usually takes ${ux.EXPECT[kind]}. You can leave this page; the run keeps going.</span>`;
    } else if (s.status === "failed") {
      el.innerHTML = `<b class="bad">Stopped at ${esc((s.stage || "start").replace("_", " "))}</b><span>${esc(s.error || "")}</span><button type="button" class="btn" data-rerun>Run again</button>`;
      const b = el.querySelector("[data-rerun]");
      b.addEventListener("click", async () => { b.disabled = true; b.innerHTML = '<span class="spin"></span>Starting'; try { await ux.rerun(kind, s.input_url); } catch (ex) { b.disabled = false; b.textContent = "Run again"; } });
    } else el.innerHTML = "";
  };
  ux.scrollActiveStage = (stagesEl) => {
    const a = stagesEl && stagesEl.querySelector(".stage.active, .stage.failed");
    if (a && stagesEl.scrollWidth > stagesEl.clientWidth) stagesEl.scrollLeft = Math.max(0, a.offsetLeft - 16);
  };
  ux.logOpen = (details, running) => { if (details && !details.dataset.touched) details.open = running; };
  document.addEventListener("click", (e) => {
    const sum = e.target.closest("#logCard > summary"); if (sum) sum.parentElement.dataset.touched = "1";
    $$("details.files[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$("details.files[open]").forEach((d) => { d.open = false; }); });

  /* a one minute summary of the finished run, rendered on the server with Remotion */
  ux.video = (slot, base, v, onStart) => {
    if (!slot) return;
    const st = (v || {}).status;
    if (st === "rendering") { slot.innerHTML = `<button class="btn" disabled><span class="spin"></span>Rendering video</button>`; return; }
    if (st === "ready") {
      slot.innerHTML = `<a class="btn" href="${base}/summary.mp4" target="_blank" rel="noopener">Play 1 min video</a><button class="btn" id="vidAgain" title="Render it again">Remake</button>`;
    } else if (st === "failed") {
      slot.innerHTML = `<button class="btn danger" id="vidAgain" title="${esc((v || {}).error || "")}">Video failed, try again</button>`;
    } else {
      slot.innerHTML = `<button class="btn" id="vidAgain">Make 1 min video</button>`;
    }
    const b = $("#vidAgain", slot);
    if (b) b.addEventListener("click", async () => {
      b.disabled = true; b.innerHTML = '<span class="spin"></span>Starting';
      try {
        const r = await fetch(`${base}/video`, {method: "POST", headers: {Accept: "application/json"}});
        const jr = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(jr.detail || `${r.status}`);
        slot.innerHTML = `<button class="btn" disabled><span class="spin"></span>Rendering video</button>`;
        if (onStart) onStart();
      } catch (ex) { slot.innerHTML = `<button class="btn danger" id="vidAgain" title="${esc(ex.message)}">Video failed, try again</button>`; }
    });
  };
  ux.goSection = (id, sel) => {
    if (ux._sections) ux._sections.show(id);
    setTimeout(() => ux.jump(sel || "#sectabs"), 30);
  };
  /* one sign-off panel, used by both tracks */
  ux.signoff = (el, cfg) => {
    const done = (c) => c.done ? " done" : "";
    if (cfg.status === "approved" && cfg.approval) {
      el.innerHTML = `<h2>Signed off</h2><div class="receipt"><b>${esc(cfg.approval.by)}</b>${esc(cfg.approval.at.replace("T", " ").slice(0, 16))} UTC<div class="note">${esc(cfg.approval.note)}</div></div>`;
      return;
    }
    if (cfg.status === "rejected" && cfg.rejection) {
      el.innerHTML = `<h2>Rejected</h2><div class="bad-banner"><b>${esc(cfg.rejection.by)}</b><p style="margin:8px 0 0">${esc(cfg.rejection.note)}</p></div>`;
      return;
    }
    if (cfg.status === "failed") {
      el.innerHTML = `<h2>Sign-off</h2><div class="bad-banner"><b>Run failed</b><p style="margin:8px 0 0">${esc(cfg.error || "")}</p></div><p class="hint">Nothing can be approved from a failed run.</p>`;
      return;
    }
    if (cfg.status !== "draft") {
      el.innerHTML = `<h2>Sign-off</h2><p class="hint"><span class="spin"></span>${esc(cfg.waiting || "Waiting for a result.")}</p>`;
      return;
    }
    el.innerHTML = `<h2>Sign-off</h2><p class="hint">You are approving ${esc(cfg.what)}. Your name and note go into the ledger and the document header.</p>
      <ul class="checks">${(cfg.checks || []).map((c, i) => `<li class="${done(c)}"><a href="#" data-check="${i}">${esc(c.label)}</a></li>`).join("")}</ul>
      ${window.__gateNote()}
      <form id="approveForm">${window.__tokenField()}
        <label class="lbl">Your name</label><input class="text" name="by" required placeholder="Full name" value="${esc(ux.name.get())}">
        <label class="lbl">What did you check?</label><textarea class="text" name="note" rows="3" required placeholder="At least 10 characters"></textarea>
        <div class="err" id="gateErr"></div>
        <div style="display:flex;gap:10px;margin-top:12px"><button class="btn primary" type="submit">${esc(cfg.approveLabel || "Approve")}</button>${cfg.reject ? '<button class="btn danger" type="button" id="rejectBtn">Reject</button>' : ""}</div>
      </form>`;
    $$("[data-check]", el).forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); const c = (cfg.checks || [])[+a.dataset.check]; if (c) ux.goSection(c.sec, c.sel);
    }));
    const form = $("#approveForm", el);
    const submit = async (action) => {
      const data = Object.fromEntries(new FormData(form).entries());
      $("#gateErr", el).textContent = "";
      if (!String(data.by || "").trim()) { $("#gateErr", el).textContent = "Your name is required."; return; }
      ux.name.set(data.by);
      try { await cfg.onSubmit(action, data); } catch (ex) { $("#gateErr", el).textContent = ex.message; }
    };
    form.addEventListener("submit", (e) => { e.preventDefault(); submit("approve"); });
    const rb = $("#rejectBtn", el); if (rb) rb.addEventListener("click", () => submit("reject"));
  };
  /* the approver's name, remembered so signing off is not retyped every time */
  ux.name = {
    get: () => { try { return localStorage.getItem("approver_name") || ""; } catch (e) { return ""; } },
    set: (v) => { try { if (v && v.trim()) localStorage.setItem("approver_name", v.trim()); } catch (e) {} },
  };
  /* in-page sections: one at a time, remembered per run */
  ux.sections = (tabsEl, defs, runId) => {
    const key = "sec:" + runId;
    let want = null; try { want = sessionStorage.getItem(key); } catch (e) {}
    const names = defs.map((d) => d.id);
    if (!names.includes(want)) want = defs.find((d) => d.attention)?.id || names[0];
    tabsEl.innerHTML = defs.map((d) => `<button type="button" data-sec="${d.id}" class="${d.id === want ? "on" : ""}">${esc(d.label)}${d.attention ? '<span class="dot"></span>' : ""}${d.n != null ? `<span class="n">${d.n}</span>` : ""}</button>`).join("");
    const show = (id) => {
      $$(".sec").forEach((el) => { el.hidden = el.dataset.sec !== id; });
      $$("button", tabsEl).forEach((b) => b.classList.toggle("on", b.dataset.sec === id));
      try { sessionStorage.setItem(key, id); } catch (e) {}
    };
    $$("button", tabsEl).forEach((b) => b.addEventListener("click", () => show(b.dataset.sec)));
    show(want);
    return { show };
  };
  ux.verdict = (el, parts) => {
    const total = parts.reduce((t, p) => t + p.n, 0) || 1;
    el.innerHTML = `<div class="meter">${parts.map((p) => p.n ? `<i class="${p.cls}" style="width:${(p.n / total) * 100}%"></i>` : "").join("")}</div>
      <div class="key">${parts.map((p) => `<span><i class="${p.cls}"></i><b>${p.n}</b> ${esc(p.label)}</span>`).join("")}</div>`;
  };

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
          return `<a class="run-row" href="${href}" title="Run ${esc(r.id)}"><div class="main"><div class="name">${esc(r.subject || r.input_url)}</div><div class="sub">${sub}</div></div>
            <div class="meta"><span class="counts">${counts}</span><span class="when">${esc(ux.ago(r.created_at))}</span></div>${chip(r.status)}</a>`;
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
    const urlIn = $("#url");
    document.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => { urlIn.value = b.dataset.fill; urlIn.focus(); }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("#runBtn"), err = $("#runErr");
      err.textContent = "";
      if (!/linkedin\.com\/in\/[^/?#\s]+/i.test($("#url").value.trim())) {
        err.textContent = "Paste a LinkedIn profile link, like https://www.linkedin.com/in/markchahwan";
        $("#url").focus(); return;
      }
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
    $("#runError").textContent = "";
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
    window.__ux.scrollActiveStage($("#stages"));
    // stats
    const c = s.counts || {};
    const n = (L.findings || []).length;
    window.__rail($("#stages"), STAGES, s.stage, ["draft", "approved", "rejected"].includes(s.status));
    window.__ux.verdict($("#verdict"), [
      {cls: "v", n: c.verified ?? 0, label: "verified"},
      {cls: "p", n: c.partially_verified ?? 0, label: "partially verified"},
      {cls: "r", n: c.unverified ?? 0, label: "refused"},
    ]);
    const ux = window.__ux;
    ux.progress($("#progress"), s, STAGES, STAGE_HINT, "diagnostic");
    ux.title(s.status, subj.full_name, "Track B");
    ux.logOpen($("#logCard"), ux.running(s));
    ux.video($("#videoSlot"), `/runs/${s.id}`, s.video, () => runPage(true));
    if (ux.running(s)) ux.bar({ spin: true, title: `Step ${Math.max(1, STAGES.indexOf(s.stage) + 1)} of ${STAGES.length}`, sub: `${esc(STAGE_HINT[s.stage] || "starting")} \u00b7 <span data-since="${esc(s.created_at)}">${ux.clock(s.created_at)}</span>` });
    else if (s.status === "draft") ux.bar({ title: "Draft ready", sub: "Needs a named approver", action: { label: "Sign off", onClick: () => ux.goSection("diagnostic", "#gate") } });
    else if (s.status === "failed") ux.bar({ title: "Run failed", sub: "The reason is under the steps", action: { label: "Run again", onClick: () => ux.rerun("diagnostic", s.input_url) } });
    else ux.bar(null);
    // the document itself, read on this page instead of a second one
    if (["draft", "approved", "rejected"].includes(s.status) && !renderRun._doc) {
      renderRun._doc = true;
      fetch(`/runs/${s.id}/diagnostic.md`).then((r) => (r.ok ? r.text() : Promise.reject())).then((t) => { $("#doc").innerHTML = md(t); }).catch(() => {});
    }
    // sections
    const F0 = L.findings || [];
    window.__ux.sections($("#sectabs"), [
      {id: "diagnostic", label: "Diagnostic"},
      {id: "findings", label: "Findings", n: F0.length},
      {id: "sources", label: "Sources", n: (L.sources || []).length},
      {id: "log", label: "Log"},
    ], s.id);
    // conflicts
    const C = L.conflicts || [];
    const conflictsHost = $("#conflicts");
    if (conflictsHost) conflictsHost.innerHTML = C.map((c) => `<div class="gap"><b class="t">${esc(c.ids.join(" and "))}</b><p>${esc(c.what)}</p>${c.claims.map((x) => `<p class="hint">${esc(x)}</p>`).join("")}${c.sources.map((u) => window.__ux.link(u)).join("")}</div>`).join("");
    // findings
    const F = L.findings || [];
    if (F.length) {
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
            ${(f.sources || []).length ? `<p><b>Sources:</b><br>${f.sources.map((u) => window.__ux.link(u)).join("")}</p>` : ""}
            <p><b>First seen:</b> ${window.__ux.link(f.origin_url)}</p>
            ${(f.passes || []).map((p, i) => `<div class="pass"><b>Pass ${i + 1} · ${esc(p.model)} · ${esc(p.verdict)}</b>
              <div>${esc(p.note || "")}${p.discrepancy ? " Discrepancy: " + esc(p.discrepancy) : ""}</div>
              ${(p.cited || []).slice(0, 2).map((c) => `<div class="ex">${esc(c.text)}<br><span class="chip ${esc(c.tier)} plain">${esc(c.tier)}</span> ${esc(window.__ux.shortUrl(c.url))}</div>`).join("")}
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
    const refused = (L.findings || []).filter((f) => f.label === "unverified").length;
    const subj = (s.subject || {}).full_name || "this subject";
    window.__ux._sections = window.__ux._sections || null;
    window.__ux.signoff(g, {
      status: s.status, approval: s.approval, rejection: s.rejection, error: s.error,
      waiting: "Waiting for the pipeline to produce a draft.",
      what: `the diagnostic for ${subj}`,
      reject: true,
      checks: [
        {label: `Read the ${refused} refused claim${refused === 1 ? "" : "s"}`, sec: "findings", sel: "#findingsSec"},
        {label: "Open at least one source", sec: "sources", sel: "#sourcesSec"},
        {label: "Read the summary and the three gaps", sec: "diagnostic", sel: "#diagnosticSec"},
      ],
      onSubmit: async (action, data) => { await postForm(`/runs/${s.id}/${action}`, data); location.reload(); },
    });
  }
  async function runPage(once) {
    const app = $("#app"); if (!app || !$("#stages") || app.dataset.kind === "radar") return;
    const rid = app.dataset.run;
    let seen = null, lines = 0;
    async function tick() {
      try {
        /* The status is a few hundred bytes; the ledger of a finished run is hundreds of kilobytes.
           Only pull the heavy documents when the run has actually moved. */
        const st = await getJSON(`/runs/${rid}/status`);
        if (st.updated_at !== seen) {
          seen = st.updated_at;
          const [d, log] = await Promise.all([getJSON(`/runs/${rid}/ledger.json`), getJSON(`/runs/${rid}/log`)]);
          lines = log.length; renderRun(d); renderLog(log);
        } else if (st.log_lines !== lines) {
          const log = await getJSON(`/runs/${rid}/log`); lines = log.length; renderLog(log);
        }
        if (!once && ["created", "running"].includes(st.status)) setTimeout(tick, 2000);
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
      window.__ux.title(s.status, subj.full_name, "Track B review");
      if (s.status === "draft") window.__ux.bar({ title: "Approve or reject", sub: "The form is after the document", action: { label: "Go to approval", onClick: () => window.__ux.jump("#gate") } });
      else window.__ux.bar(null);
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
  function mentionCard(m, L, rid, s, where) {
    const f = m.final || {}, p1 = m.pass1 || {}, p2 = m.pass2;
    const resp = (L.responses || {})[m.id];
    const ch = m.channel === "linkedin" ? "LinkedIn · snippet only, not fetched" : `${m.channel} · ${m.fetch_status || ""}`;
    let gateHtml = "";
    const inList = where === "list";
    const needs = f.ambiguous || (f.about_subject !== "no" && f.risk === "respond_now");
    if (inList) {
      if (needs) gateHtml = `<a class="btn jumpbtn" href="#act-${esc(m.id)}">${f.ambiguous ? "Decide this above" : "Review this above"}</a>`;
    } else if (f.ambiguous && s.status !== "failed") {
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
    return `<details class="mention" ${inList ? "" : `id="act-${esc(m.id)}" open`}>
      <summary><span class="fid">${esc(m.id)}</span><div><div class="title">${esc(m.title || m.url)}</div><div class="sub">${chip(m.channel)} ${m.seen_before === true ? chip("seen before", "plain") : m.seen_before === false ? chip("new", "plain") : ""} ${m.reach ? chip("reach " + m.reach.bucket, "plain") : ""} <span>${esc(m.publisher)}</span> <span>${esc(m.date || "undated")}</span> <span>${esc(m.subject)}</span></div></div>
      <div class="chips">${f.ambiguous ? chip("ambiguous") : ""}${f.about_subject === "no" ? chip("namesake", "plain") : chip(f.risk || "pending")}${f.sentiment ? chip(f.sentiment, f.sentiment + " plain") : ""}</div></summary>
      <div class="body">
        <p>${window.__ux.link(m.url)}</p>
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
  function queueItem(m, L, rid, s) {
    const f = m.final || {}, p1 = m.pass1 || {}, p2 = m.pass2 || {};
    const reading = (p, n) => p && p.model ? `<div class="reading">Pass ${n} · ${esc(p.model)} · about ${esc(p.about_subject)} · ${esc(p.risk)} · confidence ${(p.confidence ?? 0).toFixed(2)}</div>` : "";
    const opts = [
      {about: "yes", risk: "ignore", label: "It is them", sub: "nothing to do", primary: true},
      {about: "yes", risk: "watch", label: "It is them", sub: "keep watching"},
      {about: "yes", risk: "respond_now", label: "It is them", sub: "needs a reply"},
      {about: "no", risk: "ignore", label: "Not them", sub: "a namesake"},
    ];
    return `<div class="queue-item" id="act-${esc(m.id)}">
      <div class="sub">${chip(m.channel)} ${m.seen_before ? chip("seen before", "plain") : chip("new", "plain")} ${m.reach ? chip("reach " + m.reach.bucket, "plain") : ""} <span>${esc(m.publisher)}</span> <span>${esc(m.date || "undated")}</span></div>
      <h3>${esc(m.title || m.url)}</h3>
      ${window.__ux.link(m.url)}
      <p class="why">${esc(m.snippet || "")}</p>
      <p class="why"><b>Held because:</b> ${esc(f.why || "")}</p>
      <div class="readings">${reading(p1, 1)}${reading(p2, 2)}</div>
      <div class="quick">${opts.map((o) => `<button type="button" class="btn${o.primary ? " primary" : ""}" data-m="${esc(m.id)}" data-about="${o.about}" data-risk="${o.risk}">${o.label} <small>${o.sub}</small></button>`).join("")}</div>
      <div class="err"></div>
    </div>`;
  }
  function wireQueue(rid, reload) {
    document.querySelectorAll(".queue-item .quick button").forEach((b) => b.addEventListener("click", async () => {
      const item = b.closest(".queue-item"), err = $(".err", item);
      const by = window.__ux.name.get() || ($("#qname") ? $("#qname").value.trim() : "");
      if (!by) { err.textContent = "Add your name above first; decisions are recorded against it."; if ($("#qname")) $("#qname").focus(); return; }
      window.__ux.name.set(by);
      [...item.querySelectorAll("button")].forEach((x) => { x.disabled = true; });
      err.textContent = "";
      try { await postForm(`/radar/runs/${rid}/mentions/${b.dataset.m}/decide`, {by, about_subject: b.dataset.about, risk: b.dataset.risk, note: ""}); reload(); }
      catch (ex) { err.textContent = ex.message; [...item.querySelectorAll("button")].forEach((x) => { x.disabled = false; }); }
    }));
  }
  function renderRadar(d, rid) {
    const s = d.run, L = d.ledger, c = s.counts || {}, ux = window.__ux;
    $("#subject").textContent = (L.subjects || []).join(" and ") || "Profiling subjects";
    $("#meta").textContent = `${when(s.created_at)}${L.profile ? "  ·  " + (L.profile.disambiguators || []).slice(0, 3).join(" · ") : ""}`;
    const sc = $("#statusChip"); sc.className = "chip " + s.status; sc.textContent = s.status.replace(/_/g, " ");
    $("#briefLink").hidden = !["draft", "approved"].includes(s.status); $("#mdLink").hidden = $("#briefLink").hidden;
    $("#runError").textContent = "";
    const cur = STAGES.indexOf(s.stage);
    $("#stages").innerHTML = STAGES.map((st, i) => {
      let cls = ""; if (s.status === "failed" && i === cur) cls = "failed"; else if (["draft", "approved"].includes(s.status)) cls = "done"; else if (i < cur) cls = "done"; else if (i === cur) cls = "active";
      return `<div class="stage ${cls}"><b>${esc(st.replace("_", " "))}</b><span>${esc(HINT[st])}</span></div>`;
    }).join("");
    ux.scrollActiveStage($("#stages"));
    window.__rail($("#stages"), STAGES, s.stage, ["draft", "approved"].includes(s.status));
    ux.progress($("#progress"), s, STAGES, HINT, "radar");
    ux.title(s.status, (L.subjects || []).join(" and "), "Track A");
    ux.video($("#videoSlot"), `/radar/runs/${rid}`, s.video, () => radarRun(true));
    ux.verdict($("#verdict"), [
      {cls: "rn", n: c.respond_now ?? 0, label: "respond now"},
      {cls: "w", n: c.watch ?? 0, label: "watch"},
      {cls: "am", n: c.ambiguous ?? 0, label: "held for you"},
      {cls: "ig", n: c.ignore ?? 0, label: "nothing needed"},
    ]);
    if (L.profile) { $("#profileCard").hidden = false; $("#profile").innerHTML = `<p>${esc(L.profile.profile)}</p><p>${(L.profile.disambiguators || []).map((x) => chip(x, "plain")).join(" ")}</p>`; }

    const M = (L.mentions || []).filter((m) => m.final);
    const amb = M.filter((m) => m.final.ambiguous);
    const resp = M.filter((m) => !m.final.ambiguous && m.final.about_subject !== "no" && m.final.risk === "respond_now");
    const waiting = amb.length + resp.filter((m) => !(L.responses || {})[m.id] || (L.responses || {})[m.id].status === "draft").length;

    ux._sections = ux.sections($("#sectabs"), [
      {id: "queue", label: "Needs you", n: waiting, attention: waiting > 0},
      {id: "brief", label: "Brief"},
      {id: "mentions", label: "Mentions", n: M.length},
      {id: "log", label: "Log"},
    ], s.id);

    $("#queue").innerHTML = waiting
      ? `<p class="hint">Decisions are recorded against your name and carried into next week's run.</p>
         <label class="lbl">Your name</label><input class="text" id="qname" placeholder="Full name" value="${esc(ux.name.get())}">
         ${amb.length ? `<h2 style="margin:18px 0 8px">Held for you (${amb.length})</h2><p class="hint">The two readings disagreed, so the system did not guess.</p>${amb.map((m) => queueItem(m, L, rid, s)).join("")}` : ""}
         ${resp.length ? `<h2 style="margin:18px 0 8px">May need a reply (${resp.length})</h2><p class="hint">No reply exists until you approve drafting one, and the system never posts.</p>${resp.map((m) => mentionCard(m, L, rid, s, "action")).join("")}` : ""}`
      : `<p class="queue-empty">Nothing is waiting for you. ${M.length ? "Every mention was a confident call by both readings." : ""}</p>`;
    if (waiting) { wireQueue(rid, () => radarRun(true)); wireForms(rid, () => radarRun(true)); }

    if (["draft", "approved"].includes(s.status) && !renderRadar._doc) {
      renderRadar._doc = true;
      fetch(`/radar/runs/${rid}/brief.md`).then((r) => (r.ok ? r.text() : Promise.reject())).then((t) => { $("#doc").innerHTML = md(t); }).catch(() => {});
    }

    if (M.length) {
      const counts = {all: M.length, respond_now: 0, watch: 0, ignore: 0, namesake: 0};
      M.forEach((m) => { if (m.final.about_subject === "no") counts.namesake++; else counts[m.final.risk]++; });
      $("#tabs").innerHTML = ["all", "respond_now", "watch", "ignore", "namesake"].map((k) => `<button class="tab ${filter === k ? "on" : ""}" data-f="${k}">${k.replace("_", " ")} · ${counts[k]}</button>`).join("");
      $("#tabs").querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; renderRadar(d, rid); }));
      $("#mentions").innerHTML = M.filter((m) => filter === "all" || (filter === "namesake" ? m.final.about_subject === "no" : m.final.about_subject !== "no" && m.final.risk === filter)).map((m) => mentionCard(m, L, rid, s, "list")).join("") || '<div class="empty">Nothing here.</div>';
    }

    if (ux.running(s)) ux.bar({spin: true, title: `Step ${Math.max(1, STAGES.indexOf(s.stage) + 1)} of ${STAGES.length}`, sub: `${esc(HINT[s.stage] || "starting")} · <span data-since="${esc(s.created_at)}">${ux.clock(s.created_at)}</span>`});
    else if (s.status === "draft" && waiting) ux.bar({title: `${waiting} item${waiting > 1 ? "s need" : " needs"} you`, sub: "Decide, then sign off", action: {label: "Open", onClick: () => ux.goSection("queue", "#queueSec")}});
    else if (s.status === "draft") ux.bar({title: "Brief ready", sub: "Needs a named approver", action: {label: "Sign off", onClick: () => ux.jump("#gate")}});
    else if (s.status === "failed") ux.bar({title: "Run failed", sub: "The reason is under the steps", action: {label: "Run again", onClick: () => ux.rerun("radar", s.input_url)}});
    else ux.bar(null);

    ux.signoff($("#gate"), {
      status: s.status, approval: s.approval, rejection: s.rejection, error: s.error,
      waiting: "Waiting for the pipeline to produce a brief.",
      what: `this week's brief for ${(L.subjects || []).join(" and ")}`,
      approveLabel: "Approve brief",
      checks: [
        {label: waiting ? `Decide ${waiting} item${waiting > 1 ? "s" : ""} waiting for you` : "Nothing is waiting for you", sec: "queue", sel: "#queueSec", done: !waiting},
        {label: "Read the brief", sec: "brief", sel: "#briefSec"},
        {label: `Skim the ${M.length} mentions`, sec: "mentions", sel: "#mentionsSec"},
      ],
      onSubmit: async (action, data) => { await postForm(`/radar/runs/${rid}/approve`, data); location.reload(); },
    });
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
    let seen = null, lines = 0;
    async function tick() {
      try {
        const st = await getJSON(`/radar/runs/${rid}/status`);
        if (st.updated_at !== seen) {
          seen = st.updated_at;
          const [d, log] = await Promise.all([getJSON(`/radar/runs/${rid}/ledger.json`), getJSON(`/radar/runs/${rid}/log`)]);
          lines = log.length; renderRadar(d, rid); renderLog(log);
        } else if (st.log_lines !== lines) {
          const log = await getJSON(`/radar/runs/${rid}/log`); lines = log.length; renderLog(log);
        }
        if (!once && (["created", "running"].includes(st.status) || st.drafting)) setTimeout(tick, 2000);
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
      window.__ux.title(s.status, (d.ledger.subjects || []).join(" and "), "Track A brief");
      if (s.status === "draft") window.__ux.bar({ title: "Approve the brief", sub: "The form is after the brief", action: { label: "Go to approval", onClick: () => window.__ux.jump("#gate") } });
      else window.__ux.bar(null);
    } catch (ex) { $("#doc").innerHTML = `<div class="empty">${esc(ex.message)}</div>`; }
  }
  radarIndex(); radarRun(false); radarBrief();
  document.addEventListener("gate-info", () => { radarRun(true); radarBrief(); });
})();
