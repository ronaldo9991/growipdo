"""The summary video must only ever show what the run itself recorded."""
from app import config, video
from app.ledger import Run


def _diag_run(tmp_path, monkeypatch, approved=False):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    run = Run.create("https://www.linkedin.com/in/x")
    run.state.update({
        "status": "approved" if approved else "draft",
        "subject": {"full_name": "Mark Chahwan", "role": "Co-founder", "company": "Sarwa", "location": "UAE"},
        "counts": {"verified": 31, "partially_verified": 39, "unverified": 2},
    })
    if approved:
        run.state["approval"] = {"by": "Ronaldo Rajan Salamon", "note": "checked every primary source", "at": "2026-09-16T12:00:00+00:00"}
    run.ledger.update({
        "summary": "One sentence about the subject. " * 12,
        "findings": [{"label": "verified", "claim": "a", "reason": "r"}] * 70
                    + [{"label": "unverified", "claim": "Launched a year ago", "reason": "only repeated by secondary press"}] * 2,
        "gaps": [{"title": f"Gap {i}", "what_is_missing": "what is missing"} for i in range(1, 4)],
        "sources": [{"status": "ok"}] * 22 + [{"status": "could_not_check"}] * 14,
        "conflicts": [{"ids": ["F1"]}] * 9,
    })
    run.save()
    return run


def test_diagnostic_video_shows_the_run_and_nothing_else(tmp_path, monkeypatch):
    p = video.props_diagnostic(_diag_run(tmp_path, monkeypatch))
    assert p["title"] == "Mark Chahwan" and "Sarwa" in p["subtitle"]
    assert [m["n"] for m in p["meter"]] == [31, 39, 2]
    assert p["meterTitle"] == "72 claims checked"
    assert "22 of 36 pages" in p["meterNote"] and "9 conflicts" in p["meterNote"]
    assert 1 <= len(p["body"]) <= 2                      # the summary scene must stay readable
    assert len(p["items"]) == 3 and p["items"][0]["title"] == "Gap 1"
    assert p["refused"]["claim"] == "Launched a year ago"
    assert p["signoff"]["title"].startswith("Draft, waiting")


def test_approved_run_shows_the_approver(tmp_path, monkeypatch):
    p = video.props_diagnostic(_diag_run(tmp_path, monkeypatch, approved=True))
    assert p["signoff"]["title"] == "Approved by Ronaldo Rajan Salamon"
    assert "checked every primary source" in p["signoff"]["note"]


def test_radar_video_uses_the_brief_and_the_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    run = Run.create("Nidhi Hooda, Growpido", kind="radar")
    run.state.update({"status": "draft", "counts": {"about_subject": 36, "respond_now": 0, "watch": 0,
                                                     "ambiguous": 2, "ignore": 34, "linkedin": 27, "news": 0,
                                                     "web": 9, "not_subject": 4}})
    run.ledger.update({
        "subjects": ["Nidhi Hooda", "Growpido"],
        "brief": "# x\n\nWeek 2026-09-10 to 2026-09-16.\n\n## Read this first\n\n- First bullet\n- Second bullet\n- Third bullet\n\n## The week in numbers\n",
        "mentions": [
            {"id": "M1", "title": "Held item", "url": "https://x", "final": {"ambiguous": True, "about_subject": "unsure", "risk": "watch", "why": "passes disagree"}, "pass1": {"reason": "r"}},
            {"id": "M2", "title": "Namesake", "url": "https://y", "final": {"ambiguous": False, "about_subject": "no", "risk": "ignore"}, "pass1": {"reason": "a different person"}},
        ],
    })
    run.save()
    p = video.props_radar(run)
    assert p["subtitle"] == "Nidhi Hooda, Growpido · 2026-09-10 to 2026-09-16"
    assert p["meterTitle"] == "36 mentions about them"
    assert [m["n"] for m in p["meter"]] == [0, 0, 2, 34]
    assert p["body"] == ["First bullet", "Second bullet", "Third bullet"]
    assert p["items"][0]["title"] == "Held item"
    assert p["refused"]["claim"] == "Namesake" and "different person" in p["refused"]["reason"]


def test_render_refuses_clearly_when_node_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda name: None)
    ok, why = video.can_render()
    assert not ok and "Node" in why
