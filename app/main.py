"""FastAPI app: start a run, watch it, review the draft, approve or reject it."""
from __future__ import annotations

import html
import threading

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, JSONResponse

from . import pipeline
from .ledger import Run

app = FastAPI(title="prospect-diagnostic")

STYLE = """<style>
body{font-family:Georgia,serif;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}
input[type=text],textarea{width:100%;padding:.5rem;font-size:1rem;box-sizing:border-box}
button{padding:.5rem 1rem;font-size:1rem;cursor:pointer}
pre{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border:1px solid #ddd}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:.4rem;text-align:left;font-size:.95rem}
.status{font-weight:bold}.warn{color:#a40}
</style>"""


def page(title: str, body: str, refresh: bool = False) -> HTMLResponse:
    meta = '<meta http-equiv="refresh" content="5">' if refresh else ""
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'>{meta}<title>{html.escape(title)}</title>{STYLE}</head><body>{body}</body></html>")


def h(x) -> str:
    return html.escape(str(x if x is not None else ""))


@app.get("/", response_class=HTMLResponse)
def index():
    rows = []
    for rid in Run.list_ids()[:50]:
        try:
            r = Run.load(rid)
        except Exception:
            continue
        s = r.state
        subj = s.get("subject") or {}
        rows.append(
            f"<tr><td><a href='/runs/{rid}'>{rid}</a></td><td>{h(subj.get('full_name') or s.get('input_url'))}</td>"
            f"<td class='status'>{h(s['status'])}</td><td>{h(s.get('stage'))}</td><td>{h(s['created_at'])}</td></tr>"
        )
    body = f"""
<h1>Prospect diagnostic</h1>
<p>Paste a LinkedIn profile URL. LinkedIn is never fetched; the slug is resolved on the public web, every claim is
checked twice against fetched sources, and nothing leaves without a named human approving it.</p>
<form method="post" action="/run">
  <input type="text" name="url" placeholder="https://www.linkedin.com/in/..." required>
  <p><button type="submit">Run diagnostic</button></p>
</form>
<h2>Runs</h2>
<table><tr><th>Run</th><th>Subject</th><th>Status</th><th>Stage</th><th>Created</th></tr>{''.join(rows) or '<tr><td colspan=5>No runs yet.</td></tr>'}</table>
"""
    return page("Prospect diagnostic", body)


@app.post("/run")
def start_run(url: str = Form(...)):
    run = Run.create(url.strip())
    t = threading.Thread(target=_run_bg, args=(run.id,), daemon=True)
    t.start()
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


def _run_bg(run_id: str):
    run = Run.load(run_id)
    try:
        pipeline.run_pipeline(run)
    except Exception:
        pass  # the failure is already recorded in run.json and log.jsonl by run.fail()


def _load(run_id: str) -> Run:
    try:
        return Run.load(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id}")


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str):
    run = _load(run_id)
    s = run.state
    log_lines = "".join(
        f"<tr><td>{h(e['ts'][11:19])}</td><td>{h(e['stage'])}</td><td>{h(e['message'])}"
        + (f"<br><small class='warn'>{h(e['data'].get('error'))}</small>" if e.get('data', {}).get('error') else "")
        + "</td></tr>"
        for e in run.read_log()
    )
    subj = s.get("subject") or {}
    counts = s.get("counts") or {}
    links = ""
    if s["status"] in ("draft", "approved", "rejected"):
        links = (f"<p><a href='/runs/{run_id}/draft'>Open the draft for review</a> | "
                 f"<a href='/runs/{run_id}/diagnostic.md'>diagnostic.md</a> | <a href='/runs/{run_id}/ledger.json'>ledger.json</a></p>")
    err = f"<p class='warn'>Error: {h(s['error'])}</p>" if s.get("error") else ""
    body = f"""
<p><a href='/'>All runs</a></p>
<h1>Run {h(run_id)}</h1>
<p>Status: <span class='status'>{h(s['status'])}</span> (stage: {h(s.get('stage'))})</p>
<p>Input: {h(s.get('input_url'))}</p>
<p>Subject: {h(subj.get('full_name') or 'not yet identified')} {h(subj.get('role') or '')} {h(subj.get('company') or '')}</p>
<p>Counts: {h(counts.get('verified', '?'))} verified, {h(counts.get('partially_verified', '?'))} partially verified, {h(counts.get('unverified', '?'))} refused</p>
{err}{links}
<h2>Log</h2>
<table>{log_lines}</table>
"""
    return page(f"Run {run_id}", body, refresh=(s["status"] in ("created", "running")))


@app.get("/runs/{run_id}/draft", response_class=HTMLResponse)
def draft_page(run_id: str):
    run = _load(run_id)
    s = run.state
    if not run.diagnostic_path.exists():
        return page("Not ready", f"<p>Run {h(run_id)} has no draft yet (status {h(s['status'])}). <a href='/runs/{run_id}'>Back</a></p>")
    md = run.diagnostic_path.read_text(encoding="utf-8")
    warnings = run.ledger.get("lint") or []
    warn_html = ("<h2 class='warn'>House rules warnings</h2><ul>" + "".join(f"<li>{h(w)}</li>" for w in warnings) + "</ul>") if warnings else ""
    gate = ""
    if s["status"] == "draft":
        gate = f"""
<h2>Human gate</h2>
<p>Read the refused list and the sources before approving. Your name and note are recorded in the ledger.</p>
<form method="post" action="/runs/{run_id}/approve">
  <p><input type="text" name="by" placeholder="Your name" required></p>
  <p><textarea name="note" rows="3" placeholder="What did you check? (at least 10 characters)" required></textarea></p>
  <p><button type="submit">Approve</button></p>
</form>
<form method="post" action="/runs/{run_id}/reject">
  <p><input type="text" name="by" placeholder="Your name" required></p>
  <p><textarea name="note" rows="2" placeholder="Why is it rejected?" required></textarea></p>
  <p><button type="submit">Reject</button></p>
</form>"""
    else:
        gate = f"<p class='status'>This run is {h(s['status'])}.</p>"
    body = f"<p><a href='/runs/{run_id}'>Back to run</a></p>{warn_html}<pre>{h(md)}</pre>{gate}"
    return page(f"Draft {run_id}", body)


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, by: str = Form(...), note: str = Form(...)):
    run = _load(run_id)
    try:
        pipeline.approve(run, by, note)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(f"/runs/{run_id}/draft", status_code=303)


@app.post("/runs/{run_id}/reject")
def reject(run_id: str, by: str = Form(...), note: str = Form(...)):
    run = _load(run_id)
    try:
        pipeline.reject(run, by, note)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(f"/runs/{run_id}/draft", status_code=303)


@app.get("/runs/{run_id}/diagnostic.md")
def diagnostic_md(run_id: str):
    run = _load(run_id)
    if not run.diagnostic_path.exists():
        raise HTTPException(404, "no diagnostic yet")
    return PlainTextResponse(run.diagnostic_path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/runs/{run_id}/ledger.json")
def ledger_json(run_id: str):
    run = _load(run_id)
    return JSONResponse({"run": run.state, "ledger": run.ledger})


@app.get("/runs/{run_id}/log")
def log_json(run_id: str):
    run = _load(run_id)
    return JSONResponse(run.read_log())


@app.get("/health")
def health():
    return {"ok": True}
