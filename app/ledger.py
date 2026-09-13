"""Run state on disk: runs/<id>/run.json, log.jsonl, ledger.json, diagnostic.md."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import config
from .util import now_iso, new_run_id


class Run:
    def __init__(self, run_id: str, folder: Path):
        self.id = run_id
        self.folder = folder
        self.state: dict = {
            "id": run_id,
            "status": "created",
            "stage": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "input_url": "",
            "subject": {},
            "models": {},
            "approval": None,
            "error": None,
            "counts": {},
        }
        self.ledger: dict = {"sources": [], "claims": [], "findings": [], "gaps": [], "summary": "", "lint": []}

    @classmethod
    def create(cls, input_url: str) -> "Run":
        run_id = new_run_id()
        run.save()
        run.log("run", "created", url=input_url)
        return run

    @classmethod
    def load(cls, run_id: str) -> "Run":
        folder = config.RUNS_DIR / run_id
        if not (folder / "run.json").exists():
            raise FileNotFoundError(f"no run {run_id}")
        run = cls(run_id, folder)
        run.state = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        lp = folder / "ledger.json"
        if lp.exists():
            run.ledger = json.loads(lp.read_text(encoding="utf-8"))
        return run

    @staticmethod
    def list_ids() -> list[str]:
        if not config.RUNS_DIR.exists():
            return []
        return sorted([p.name for p in config.RUNS_DIR.iterdir() if (p / "run.json").exists()], reverse=True)

    def save(self) -> None:
        self.state["updated_at"] = now_iso()
        (self.folder / "run.json").write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        (self.folder / "ledger.json").write_text(json.dumps(self.ledger, indent=2, ensure_ascii=False), encoding="utf-8")

    def log(self, stage: str, message: str, **data) -> None:
        entry = {"ts": now_iso(), "stage": stage, "message": message}
        if data:
            entry["data"] = data
        with open(self.folder / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def set_stage(self, stage: str) -> None:
        self.state["stage"] = stage
        self.state["status"] = "running"
        self.save()
        self.log(stage, "started")

    def fail(self, exc: BaseException) -> None:
        self.state["status"] = "failed"
        self.state["error"] = f"{type(exc).__name__}: {exc}"
        self.save()
        self.log(self.state.get("stage") or "run", "failed", error=self.state["error"],
                 traceback=traceback.format_exc()[-4000:])

    def read_log(self) -> list[dict]:
        p = self.folder / "log.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    @property
    def diagnostic_path(self) -> Path:
        return self.folder / "diagnostic.md"

    @property
    def brief_path(self) -> Path:
        return self.folder / "brief.md"
