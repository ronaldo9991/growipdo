"""Weekly scheduler for Track A. In process, one daemon thread, no external service.

RADAR_SCHEDULE is "<weekday> <HH:MM>" in UTC, for example "mon 09:00". When the moment passes and no
scheduled run started in the last 20 hours, a radar run is created for RADAR_SUBJECTS. The last start is
recorded in runs/radar/schedule.json so a restart does not double run."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_schedule(text: str) -> tuple[int, int, int] | None:
    m = re.match(r"^\s*([a-z]{3})\w*\s+(\d{1,2}):(\d{2})\s*$", (text or "").lower())
    if not m or m.group(1) not in DAYS:
        return None
    h, mi = int(m.group(2)), int(m.group(3))
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    return DAYS.index(m.group(1)), h, mi


def next_fire(now: datetime, spec: tuple[int, int, int]) -> datetime:
    day, h, mi = spec
    candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    delta = (day - now.weekday()) % 7
    candidate = candidate + timedelta(days=delta)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def due(now: datetime, spec: tuple[int, int, int], last_start: datetime | None) -> bool:
    """True when the scheduled moment for this week has passed and we have not run since."""
    day, h, mi = spec
    this = now.replace(hour=h, minute=mi, second=0, microsecond=0) - timedelta(days=(now.weekday() - day) % 7)
    if this > now:
        this -= timedelta(days=7)
    if now - this > timedelta(hours=20):
        return False  # missed by more than a working day: wait for next week rather than run at a random time
    return last_start is None or last_start < this


def _state_path():
    return config.RUNS_DIR / "radar" / "schedule.json"


def read_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(state: dict) -> None:
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def status() -> dict:
    spec = parse_schedule(config.RADAR_SCHEDULE)
    st = read_state()
    now = datetime.now(timezone.utc)
    return {"enabled": bool(spec), "schedule": config.RADAR_SCHEDULE or None, "subjects": config.RADAR_SUBJECTS,
            "next": next_fire(now, spec).isoformat() if spec else None,
            "last_start": st.get("last_start"), "last_run_id": st.get("last_run_id")}


def start(run_factory) -> threading.Thread | None:
    """run_factory(subjects) creates and runs a radar run and returns its id."""
    spec = parse_schedule(config.RADAR_SCHEDULE)
    if not spec:
        return None

    def loop():
        while True:
            try:
                st = read_state()
                last = datetime.fromisoformat(st["last_start"]) if st.get("last_start") else None
                now = datetime.now(timezone.utc)
                if due(now, spec, last):
                    write_state({"last_start": now.isoformat(), "last_run_id": None})
                    rid = run_factory(config.RADAR_SUBJECTS)
                    write_state({"last_start": now.isoformat(), "last_run_id": rid})
            except Exception:
                pass  # the run records its own failure; the scheduler keeps ticking
            time.sleep(60)

    t = threading.Thread(target=loop, daemon=True, name="radar-scheduler")
    t.start()
    return t
