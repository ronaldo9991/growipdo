"""FastAPI app for both tracks.

Track B (prospect to diagnostic): /diagnostic, /run, /runs/{id}...
Track A (reputation radar):       /radar, /radar/run, /radar/runs/{id}...
Pages are static shells under app/templates rendered by JavaScript from the JSON endpoints, so what the
reviewer sees is the data in the ledger."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, radar
from .ledger import Run

app = FastAPI(title="growpido-task")
HERE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

_TEMPLATES = {p.stem: p.read_text(encoding="utf-8") for p in (HERE / "templates").glob("*.html")}


def page(name: str, title: str, track: str = "", **vars) -> HTMLResponse:
    html = _TEMPLATES["_head"] + _TEMPLATES[name] + _TEMPLATES["_foot"]
    vars = {"title": title, "script": "", "track": track, **vars}
    for k, v in vars.items():
        html = html.replace("{{" + k + "}}", str(v))
    return HTMLResponse(html)


def wants_json(request: Request) -> bool:
    return "application/json" in (request.headers.get("accept") or "")


def _load(run_id: str, kind: str = "diagnostic") -> Run:
    if not run_id.replace("-", "").isalnum():
        raise HTTPException(404, "bad run id")
    try:
        return Run.load(run_id, kind)
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id}")


def _bg(fn, run_id: str, kind: str):
    run = Run.load(run_id, kind)
    try:
        fn(run)
    except Exception:
        pass  # already recorded in run.json and log.jsonl by run.fail()


def _list(kind: str) -> list[dict]:
    out = []
    for rid in Run.list_ids(kind)[:100]:
        try:
            r = Run.load(rid, kind)
        except Exception:
            continue
        s = r.state
        subj = s.get("subject") or {}
        out.append({"id": rid, "status": s["status"], "stage": s.get("stage"), "created_at": s["created_at"],
                    "input_url": s.get("input_url"), "subject": subj.get("full_name"), "role": subj.get("role"),
                    "company": subj.get("company"), "counts": s.get("counts") or {}})
    return out


# ---------- home ----------

@app.get("/", response_class=HTMLResponse)
def home():
    return page("home", "Growpido Task")


@app.get("/health")
def health():
    return {"ok": True}


# ---------- Track B ----------

@app.get("/diagnostic", response_class=HTMLResponse)
def diagnostic_index():
    return page("diagnostic", "Track B · Prospect Diagnostic", track="b")


@app.get("/api/runs")
def api_runs():
    return _list("diagnostic")


@app.post("/run")
def start_run(request: Request, url: str = Form(...)):
    url = url.strip()
    if "linkedin.com/in/" not in url.lower():
        msg = "Paste a LinkedIn profile URL of the form https://www.linkedin.com/in/<slug>"
        if wants_json(request):
            raise HTTPException(400, msg)
        return page("diagnostic", "Track B · Prospect Diagnostic", track="b")
    run = Run.create(url)
    threading.Thread(target=_bg, args=(pipeline.run_pipeline, run.id, "diagnostic"), daemon=True).start()
    if wants_json(request):
        return {"id": run.id}
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str):
    _load(run_id)
    return page("run", f"Run {run_id}", track="b", run_id=run_id)


@app.get("/runs/{run_id}/draft", response_class=HTMLResponse)
def draft_page(run_id: str):
    _load(run_id)
    return page("draft", f"Draft {run_id}", track="b", run_id=run_id)


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


# ---------- Track A ----------

@app.get("/radar", response_class=HTMLResponse)
def radar_index():
    return page("radar", "Track A · Reputation Radar", track="a")


@app.get("/api/radar/runs")
def api_radar_runs():
    return _list("radar")


@app.post("/radar/run")
def radar_start(request: Request, subjects: str = Form(...)):
    subs = radar.parse_subjects(subjects)
    if not subs:
        raise HTTPException(400, "Give at least one subject name")
    run = Run.create(", ".join(subs), kind="radar")
    threading.Thread(target=_bg, args=(radar.run_radar, run.id, "radar"), daemon=True).start()
    if wants_json(request):
        return {"id": run.id}
    return RedirectResponse(f"/radar/runs/{run.id}", status_code=303)


@app.get("/radar/runs/{run_id}", response_class=HTMLResponse)
def radar_run_page(run_id: str):
    _load(run_id, "radar")
    return page("radar_run", f"Radar {run_id}", track="a", run_id=run_id)


@app.get("/radar/runs/{run_id}/brief", response_class=HTMLResponse)
def radar_brief_page(run_id: str):
    _load(run_id, "radar")
    return page("radar_brief", f"Brief {run_id}", track="a", run_id=run_id)


@app.get("/radar/runs/{run_id}/brief.md")
def radar_brief_md(run_id: str):
    run = _load(run_id, "radar")
    if not run.brief_path.exists():
        raise HTTPException(404, "no brief yet")
    return PlainTextResponse(run.brief_path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/radar/runs/{run_id}/ledger.json")
def radar_ledger(run_id: str):
    run = _load(run_id, "radar")
    return JSONResponse({"run": run.state, "ledger": run.ledger})


@app.get("/radar/runs/{run_id}/log")
def radar_log(run_id: str):
    return JSONResponse(_load(run_id, "radar").read_log())


def _guard(fn, *args):
    try:
        return fn(*args)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/radar/runs/{run_id}/approve")
def radar_approve(run_id: str, by: str = Form(...), note: str = Form(...)):
    run = _load(run_id, "radar")
    _guard(radar.approve_brief, run, by, note)
    return {"ok": True, "status": run.state["status"]}


@app.post("/radar/runs/{run_id}/mentions/{mention_id}/decide")
def radar_decide(run_id: str, mention_id: str, by: str = Form(...), about_subject: str = Form(...),
                 risk: str = Form(...), note: str = Form("")):
    run = _load(run_id, "radar")
    _guard(radar.resolve_ambiguous, run, mention_id, by, about_subject, risk, note)
    return {"ok": True}


@app.post("/radar/runs/{run_id}/mentions/{mention_id}/request")
def radar_request(run_id: str, mention_id: str, by: str = Form(...), note: str = Form(...)):
    """Gate 1: the human approves drafting. The draft is written in the background so the page stays live."""
    run = _load(run_id, "radar")
    m = next((x for x in run.ledger.get("mentions", []) if x["id"] == mention_id), None)
    if not m:
        raise HTTPException(404, "no such mention")
    if (run.ledger.get("responses") or {}).get(mention_id):
        raise HTTPException(400, "a response request already exists for this mention")
    if not by.strip() or len(note.strip()) < 5:
        raise HTTPException(400, "drafting needs a name and a short note")

    def work():
        r = Run.load(run_id, "radar")
        try:
            radar.request_response(r, mention_id, by, note)
        except Exception as e:
            r.ledger.setdefault("responses", {})[mention_id] = {"status": "declined", "declined_by": "system",
                                                                  "decline_note": f"drafting failed: {e}"}
            r.save()
            r.log("response", f"{mention_id}: drafting failed", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "status": "drafting"}


@app.post("/radar/runs/{run_id}/mentions/{mention_id}/approve")
def radar_approve_response(run_id: str, mention_id: str, by: str = Form(...), note: str = Form(""), edited: str = Form("")):
    run = _load(run_id, "radar")
    _guard(radar.approve_response, run, mention_id, by, note, edited)
    return {"ok": True}


@app.post("/radar/runs/{run_id}/mentions/{mention_id}/decline")
def radar_decline_response(run_id: str, mention_id: str, by: str = Form(...), note: str = Form("")):
    run = _load(run_id, "radar")
    _guard(radar.decline_response, run, mention_id, by, note)
    return {"ok": True}
