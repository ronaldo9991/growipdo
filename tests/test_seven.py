"""Tests for the seven additions: conflicts, concurrency, scheduler, memory, token, evidence zip, reach."""
from datetime import datetime, timezone

import pytest

from app import config, radar, report, scheduler
from app.ledger import Run


# 1. conflicts between sources
def _f(fid, claim, cat="funding", label="verified", discrepancy=None, sources=None):
    return {"id": fid, "claim": claim, "category": cat, "label": label, "origin_url": "u", "sources": sources or ["https://a"],
            "passes": [{"verdict": "supported", "discrepancy": discrepancy, "cited": [{"url": "https://a"}]}, {"verdict": "supported", "discrepancy": None, "cited": []}]}


def test_conflicts_from_discrepancy_and_from_numbers():
    fs = [_f("F1", "USD 2 million in commitments from over 150 potential investors", discrepancy="ADGM says 144 investors and USD 2.1 million"),
          _f("F2", "144 investors subscribed to the offer and committed approximately USD 2.1 million"),
          _f("F3", "Sarwa raised USD 15 million in its Series B", label="partially_verified"),
          _f("F4", "Sarwa raised USD 25 million in its Series B", label="unverified"),
          _f("F5", "Sarwa raised more than US$ 8.4 million in its Series A", label="partially_verified"),
          _f("F6", "The DFSA fined Sarwa Digital Wealth USD 191,100 for the public offer", cat="regulatory"),
          _f("F7", "The FSRA ordered Sarwa Digital Wealth to pay a Dh449,881 penalty for the public offer", cat="regulatory",
             discrepancy="E6 says Retail Client Endorsement rather than Retail Client"),
          _f("F8", "The penalty was USD 390,000 (AED 1,432,275) before discounts for the public offer", cat="regulatory"),
          _f("F9", "Sarwa Digital Wealth (Capital) Limited holds licence 190037 for the public offer business", cat="regulatory"),
          _f("F10", "Sarwa was licensed in 2020 for the public offer business", cat="regulatory"),
          _f("F11", "Sarwa was licensed in 2018 for the public offer business", cat="regulatory")]
    out = report.find_conflicts(fs)
    kinds = [tuple(c["ids"]) for c in out]
    assert ("F1",) in kinds                        # discrepancy with a figure
    assert ("F1", "F2") in kinds                   # 150 versus 144, 2 million versus 2.1 million
    assert not any("F4" in c["ids"] for c in out)  # refused findings are refused, not conflicts
    assert ("F3", "F5") not in kinds               # two different rounds, far apart numbers
    assert ("F6", "F7") not in kinds               # two different fines by two regulators
    assert ("F7",) not in kinds                    # a wording discrepancy with no figure is not a conflict
    assert ("F7", "F8") not in kinds               # AED 449,881 against USD 390,000: different currencies
    assert ("F6", "F9") not in kinds               # a licence number is not a figure
    assert ("F10", "F11") not in kinds             # years are dates, not figures to reconcile


# 2. concurrent verification keeps order
def test_verify_claims_runs_concurrently_in_order(tmp_path, monkeypatch):
    from app import verify
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "VERIFY_WORKERS", 4)
    snap = tmp_path / "s.txt"; snap.write_text("url: x\n---\n" + "The fine was USD 191,100 for the offer. " * 20)
    sources = [{"id": "S1", "url": "https://www.dfsa.ae/x", "tier": "primary", "status": "ok", "snapshot": str(snap)}]

    class FakeLLM:
        model = "fake"
        def json(self, system, user, max_tokens=0):
            return {"verdict": "supported", "supporting_excerpts": ["E1"], "relayed_excerpts": [], "discrepancy": None, "note": "n"}
    claims = [{"id": f"C{i}", "text": f"claim number {i} about the fine USD 191,100", "quote": "", "category": "regulatory", "about": "company",
               "numbers": ["191,100"], "origin": "S1", "origin_url": "https://www.dfsa.ae/x", "origin_tier": "primary"} for i in range(1, 9)]
    out = verify.verify_claims(claims, sources, FakeLLM(), FakeLLM(), lambda *a, **k: None)
    assert [f["claim_id"] for f in out] == [f"C{i}" for i in range(1, 9)]
    assert all(f["label"] == "verified" for f in out)


# 3. scheduler
def test_schedule_parse_next_and_due():
    assert scheduler.parse_schedule("mon 09:00") == (0, 9, 0)
    assert scheduler.parse_schedule("Monday 09:00") == (0, 9, 0)
    assert scheduler.parse_schedule("someday 09:00") is None and scheduler.parse_schedule("mon 25:00") is None
    spec = (0, 9, 0)
    wed = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    assert scheduler.next_fire(wed, spec) == datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
    mon_0930 = datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)
    assert scheduler.due(mon_0930, spec, None)
    assert not scheduler.due(mon_0930, spec, datetime(2026, 9, 14, 9, 5, tzinfo=timezone.utc))   # already ran
    assert not scheduler.due(wed, spec, None)   # missed by more than 20 hours: wait for next week
    assert not scheduler.due(datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc), spec, None)  # not yet


# 4. memory between weeks
def test_previous_mentions_and_mark_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    old = Run.create("Nidhi Hooda", kind="radar")
    old.ledger["mentions"] = [{"id": "M1", "url": "https://www.linkedin.com/posts/x?utm=1", "final": {"risk": "watch", "decided_by": "R"}}]
    old.state["status"] = "approved"; old.save()
    new = Run.create("Nidhi Hooda", kind="radar")
    pid, prev = radar.previous_mentions(new.id)
    assert pid == old.id
    ms = [{"url": "https://linkedin.com/posts/x/"}, {"url": "https://other.example/y"}]
    radar.mark_seen(ms, prev)
    assert ms[0]["seen_before"] and ms[0]["seen_as"]["risk"] == "watch" and ms[0]["seen_as"]["run"] == old.id
    assert not ms[1]["seen_before"]


def test_human_decision_is_carried_forward(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    old = Run.create("Nidhi Hooda", kind="radar")
    old.ledger["mentions"] = [{"id": "M5", "url": "https://x/1", "final": {"about_subject": "no", "risk": "ignore", "ambiguous": False, "why": "namesake", "decided_by": "Ronaldo"}},
                              {"id": "M6", "url": "https://x/2", "final": {"about_subject": "yes", "risk": "watch", "ambiguous": True, "why": "split"}}]
    old.state["status"] = "approved"; old.save()
    new = Run.create("Nidhi Hooda", kind="radar")
    _, prev = radar.previous_mentions(new.id)
    ms = [{"url": "https://x/1", "pass1": {"sentiment": "neutral"}}, {"url": "https://x/2", "pass1": {"sentiment": "neutral"}}]
    radar.mark_seen(ms, prev)
    f = radar.carry_forward(ms[0])
    assert f and f["about_subject"] == "no" and f["risk"] == "ignore" and not f["ambiguous"] and "Ronaldo" in f["why"] and f["carried_from"] == old.id
    assert radar.carry_forward(ms[1]) is None   # an undecided ambiguous item is not carried, it is asked again


# 5. approver token
def _client(monkeypatch, tmp_path, token):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(config, "EVIDENCE_DIR", tmp_path / "ev")
    monkeypatch.setattr(config, "APPROVER_TOKEN", token)
    monkeypatch.setattr(config, "RADAR_SCHEDULE", "")
    return TestClient(main.app)


def _draft_b(tmp_path):
    run = Run.create("https://www.linkedin.com/in/x")
    run.state.update({"status": "draft", "subject": {"full_name": "X", "role": "CEO", "company": "Co", "location": "UAE"},
                      "models": {"primary": "a", "second_opinion": "b"}})
    run.ledger.update({"sources": [], "findings": [], "gaps": [], "summary": "s", "lint": []})
    run.save()
    run.diagnostic_path.write_text("# x\n\nStatus: DRAFT\n", encoding="utf-8")
    return run


def test_gate_requires_token_when_configured(tmp_path, monkeypatch):
    c = _client(monkeypatch, tmp_path, "secret")
    run = _draft_b(tmp_path)
    assert c.get("/api/gate").json() == {"token_required": True}
    r = c.post(f"/runs/{run.id}/approve", data={"by": "R", "note": "checked everything"}, headers={"Accept": "application/json"})
    assert r.status_code == 403
    r = c.post(f"/runs/{run.id}/approve", data={"by": "R", "note": "checked everything", "token": "wrong"}, headers={"Accept": "application/json"})
    assert r.status_code == 403
    r = c.post(f"/runs/{run.id}/approve", data={"by": "R", "note": "checked everything", "token": "secret"}, headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_gate_open_when_no_token(tmp_path, monkeypatch):
    c = _client(monkeypatch, tmp_path, "")
    run = _draft_b(tmp_path)
    assert c.get("/api/gate").json() == {"token_required": False}
    r = c.post(f"/runs/{run.id}/approve", data={"by": "R", "note": "checked everything"}, headers={"Accept": "application/json"})
    assert r.status_code == 200


# 6. evidence bundle
def test_evidence_zip_contains_run_and_snapshots(tmp_path, monkeypatch):
    import io, zipfile
    c = _client(monkeypatch, tmp_path, "")
    run = _draft_b(tmp_path)
    ev = tmp_path / "ev" / run.id; ev.mkdir(parents=True)
    (ev / "abc.txt").write_text("url: x\n---\nsnapshot", encoding="utf-8")
    r = c.get(f"/runs/{run.id}/evidence.zip")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert f"{run.id}/run/ledger.json" in names and f"{run.id}/evidence/abc.txt" in names


# 7. reach
def test_reach_and_bump():
    m = {"title": "Nidhi Hooda | 82 comments - LinkedIn", "snippet": "", "channel": "linkedin"}
    r = radar.reach_of(m)
    assert r["engagement"] == 82 and r["bucket"] == "high" and "82 comments" in r["signals"]
    low = radar.reach_of({"title": "About page", "snippet": "", "channel": "web"})
    assert low["bucket"] == "low"
    final = {"about_subject": "yes", "risk": "ignore", "sentiment": "negative", "ambiguous": False, "why": "both agree"}
    assert radar.apply_reach(final, r)["risk"] == "watch"
    assert radar.apply_reach(final, low)["risk"] == "ignore"
    assert radar.apply_reach({**final, "sentiment": "positive"}, r)["risk"] == "ignore"
