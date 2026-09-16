"""One minute summary videos, rendered with Remotion from a run's own ledger.

Nothing here invents content: every line in the video comes from the run that produced it, so a number
on screen can be traced back to a finding, a mention or the approval record."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import config
from .ledger import Run
from .util import now_iso

VIDEO_DIR = config.ROOT / "video"
OK = "#8fd9a8"
WARN = "#e8c46a"
BAD = "#f08a8a"
AMB = "#c9b8f5"
GREY = "rgba(225,224,204,0.25)"
FOOTER = "LinkedIn is never fetched. Nothing leaves without a named approver."


def _chunks(text: str, words_per: int = 40, most: int = 2) -> list[str]:
    """A paragraph split into a few readable blocks, whole sentences where possible."""
    out, cur = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        cur.append(sentence)
        if len(" ".join(cur).split()) >= words_per:
            out.append(" ".join(cur))
            cur = []
        if len(out) >= most:
            break
    if cur and len(out) < most:
        out.append(" ".join(cur))
    return out or ["No summary was written for this run."]


def _signoff(s: dict) -> dict:
    a = s.get("approval")
    if a:
        return {"kicker": "Human gate", "title": f"Approved by {a['by']}", "note": a.get("note") or ""}
    r = s.get("rejection")
    if r:
        return {"kicker": "Human gate", "title": f"Rejected by {r['by']}", "note": r.get("note") or ""}
    return {"kicker": "Human gate", "title": "Draft, waiting for a named approver",
            "note": "Nothing reaches a client until a person signs it with their name."}


def props_diagnostic(run: Run) -> dict:
    s, L = run.state, run.ledger
    subj = s.get("subject") or {}
    F = L.get("findings") or []
    c = s.get("counts") or {}
    sources = L.get("sources") or []
    readable = sum(1 for x in sources if x.get("status") == "ok")
    refused = [f for f in F if f["label"] == "unverified"]
    gaps = L.get("gaps") or []
    conflicts = len(L.get("conflicts") or [])
    return {
        "kicker": "Track B, prospect diagnostic",
        "title": subj.get("full_name") or "Prospect diagnostic",
        "subtitle": " · ".join([x for x in (subj.get("role"), subj.get("company"), subj.get("location")) if x]),
        "runLine": f"Run {s['id']} · {s['created_at'][:10]}",
        "meterKicker": "Checked twice, against primary sources",
        "meterTitle": f"{len(F)} claims checked",
        "meter": [
            {"label": "verified", "n": c.get("verified", 0), "color": OK},
            {"label": "partially verified", "n": c.get("partially_verified", 0), "color": WARN},
            {"label": "refused", "n": c.get("unverified", 0), "color": BAD},
        ],
        "meterNote": f"{readable} of {len(sources)} pages read and archived"
                     + (f" · {conflicts} conflict{'s' if conflicts != 1 else ''} between sources" if conflicts else ""),
        "bodyKicker": "Summary",
        "body": _chunks(L.get("summary") or ""),
        "itemsKicker": "Three biggest gaps",
        "items": [{"title": g.get("title") or "", "note": g.get("what_is_missing") or ""} for g in gaps[:3]],
        "refusedKicker": "One claim the system refused",
        "refused": {"claim": refused[0]["claim"], "reason": refused[0]["reason"]} if refused
                   else {"claim": "No claim was refused in this run.", "reason": ""},
        "signoff": _signoff(s),
        "footer": FOOTER,
    }


def props_radar(run: Run) -> dict:
    s, L = run.state, run.ledger
    c = s.get("counts") or {}
    M = [m for m in (L.get("mentions") or []) if m.get("final")]
    subjects = ", ".join(L.get("subjects") or [])
    held = [m for m in M if m["final"].get("ambiguous")]
    respond = [m for m in M if not m["final"].get("ambiguous") and m["final"].get("about_subject") != "no"
               and m["final"].get("risk") == "respond_now"]
    namesakes = [m for m in M if m["final"].get("about_subject") == "no"]
    brief = L.get("brief") or ""
    opening = re.search(r"## Read this first\n+(.*?)\n\n", brief, re.S)
    bullets = [b.strip("- ").strip() for b in (opening.group(1).splitlines() if opening else []) if b.strip()]
    week = re.search(r"Week (\d{4}-\d\d-\d\d) to (\d{4}-\d\d-\d\d)", brief)
    items = [{"title": m["title"] or m["url"], "note": m["final"].get("why") or ""} for m in (respond + held)[:3]]
    return {
        "kicker": "Track A, reputation radar",
        "title": "Weekly brief",
        "subtitle": subjects + (f" · {week.group(1)} to {week.group(2)}" if week else ""),
        "runLine": f"Run {s['id']} · {s['created_at'][:10]}",
        "meterKicker": "Every mention, triaged twice",
        "meterTitle": f"{c.get('about_subject', len(M))} mentions about them",
        "meter": [
            {"label": "respond now", "n": c.get("respond_now", 0), "color": BAD},
            {"label": "watch", "n": c.get("watch", 0), "color": WARN},
            {"label": "held for you", "n": c.get("ambiguous", 0), "color": AMB},
            {"label": "nothing needed", "n": c.get("ignore", 0), "color": GREY},
        ],
        "meterNote": f"{c.get('linkedin', 0)} LinkedIn, {c.get('news', 0)} news, {c.get('web', 0)} web"
                     f" · {c.get('not_subject', 0)} set aside as namesakes",
        "bodyKicker": "Read this first",
        "body": bullets[:3] or ["The brief had no opening bullets."],
        "itemsKicker": "What needs you" if items else "Nothing needed a decision",
        "items": items,
        "refusedKicker": "Set aside as a namesake",
        "refused": {"claim": namesakes[0]["title"] if namesakes else "No namesake was found this week.",
                    "reason": (namesakes[0]["pass1"]["reason"] if namesakes else "")},
        "signoff": _signoff(s),
        "footer": FOOTER,
    }


def can_render() -> tuple[bool, str]:
    if not shutil.which("npx"):
        return False, "Node is not installed on this machine, so the video cannot be rendered here."
    if not (VIDEO_DIR / "node_modules").exists():
        return False, "The video dependencies are not installed. Run npm install inside the video folder."
    return True, ""


def render(run: Run, kind: str) -> Path:
    """Blocking render. Callers run this on a background thread and watch run.state['video']."""
    ok, why = can_render()
    if not ok:
        raise RuntimeError(why)
    props = props_radar(run) if kind == "radar" else props_diagnostic(run)
    props_path = run.folder / "video_props.json"
    props_path.write_text(json.dumps({"data": props}, ensure_ascii=False, indent=2), encoding="utf-8")
    out = run.folder / "summary.mp4"
    composition = "TrackA" if kind == "radar" else "TrackB"
    cmd = ["npx", "--yes", "remotion", "render", "src/index.jsx", composition, str(out),
           f"--props={props_path}", "--log=error", "--concurrency=2"]
    run.log("video", f"rendering {composition} with Remotion")
    proc = subprocess.run(cmd, cwd=VIDEO_DIR, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not out.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise RuntimeError("remotion render failed: " + " | ".join(tail))
    return out


def start(run: Run, kind: str) -> None:
    """Mark the run as rendering, render, then record the result on the run."""
    run.state["video"] = {"status": "rendering", "started_at": now_iso()}
    run.save()
    try:
        out = render(run, kind)
        run.state["video"] = {"status": "ready", "started_at": run.state["video"]["started_at"],
                              "finished_at": now_iso(), "bytes": out.stat().st_size}
        run.log("video", f"summary video ready, {out.stat().st_size // 1024} KB")
    except Exception as e:
        run.state["video"] = {"status": "failed", "error": str(e)[:400], "finished_at": now_iso()}
        run.log("video", "video render failed", error=str(e)[:400])
    run.save()
