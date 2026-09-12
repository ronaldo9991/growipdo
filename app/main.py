"""FastAPI app: start a run, watch it live, review the draft, approve or reject it.

Pages are static shells under app/templates rendered by JavaScript from the JSON endpoints below,
so the same data the reviewer sees is the data in the ledger."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline
from .ledger import Run

app = FastAPI(title="prospect-diagnostic")
HERE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

_TEMPLATES = {p.stem: p.read_text(encoding="utf-8") for p in (HERE / "templates").glob("*.html")}


def page(name: str, title: str, **vars) -> HTMLResponse:
    body = _TEMPLATES[name]
    html = _TEMPLATES["_head"] + body + _TEMPLATES["_foot"]
    vars = {"title": title, "script": "", **vars}
    for k, v in vars.items():
        html = html.replace("{{" + k + "}}", str(v))
    return HTMLResponse(html)


def wants_json(request: Request) -> bool:
    return "application/json" in (request.headers.get("accept") or "")


def _load(run_id: str) -> Run:
    if not run_id.replace("-", "").isalnum():
        raise HTTPException(404, "bad run id")
    try:
        return Run.load(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id}")


def _run_bg(run_id: str):
    run = Run.load(run_id)
    try:
        pipeline.run_pipeline(run)
    except Exception:
        pass  # already recorded in run.json and log.jsonl by run.fail()


@app.get("/", response_class=HTMLResponse)
def index():
    return page("index", "Prospect Diagnostic")


@app.get("/api/runs")
def api_runs():
    out = []
    for rid in Run.list_ids()[:100]:
        try:
            r = Run.load(rid)
        except Exception:
            continue
        s = r.state
        subj = s.get("subject") or {}
        out.append({"id": rid, "status": s["status"], "stage": s.get("stage"), "created_at": s["created_at"],
                    "input_url": s.get("input_url"), "subject": subj.get("full_name"), "role": subj.get("role"),
                    "company": subj.get("company"), "counts": s.get("counts") or {}})
    return out


@app.post("/run")
def start_run(request: Request, url: str = Form(...)):
    url = url.strip()
    if "linkedin.com/in/" not in url.lower():
        msg = "Paste a LinkedIn profile URL of the form https://www.linkedin.com/in/<slug>"
        if wants_json(request):
            raise HTTPException(400, msg)
        return page("index", "Prospect Diagnostic")
    run = Run.create(url)
    threading.Thread(target=_run_bg, args=(run.id,), daemon=True).start()
    if wants_json(request):
        return {"id": run.id}
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str):
    _load(run_id)
    return page("run", f"Run {run_id}", run_id=run_id)


@app.get("/runs/{run_id}/draft", response_class=HTMLResponse)
def draft_page(run_id: str):
    _load(run_id)
    return page("draft", f"Draft {run_id}", run_id=run_id)


@app.post("/runs/{run_id}/approve")
def approve(request: Request, run_id: str, by: str = Form(...), note: str = Form(...)):
    run = _load(run_id)
    try:
        pipeline.approve(run, by, note)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    if wants_json(request):
        return {"ok": True, "status": run.state["status"]}
    return RedirectResponse(f"/runs/{run_id}/draft", status_code=303)


@app.post("/runs/{run_id}/reject")
def reject(request: Request, run_id: str, by: str = Form(...), note: str = Form(...)):
    run = _load(run_id)
    try:
        pipeline.reject(run, by, note)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    if wants_json(request):
        return {"ok": True, "status": run.state["status"]}
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
    return JSONResponse(_load(run_id).read_log())


@app.get("/health")
def health():
    return {"ok": True}
