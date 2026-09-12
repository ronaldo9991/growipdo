from app import report


def _finding(fid, label, claim, cited_text=""):
    return {"id": fid, "label": label, "claim": claim, "quote": "", "category": "traction", "about": "company",
            "numbers": [], "origin_url": "u", "origin_tier": "company", "also_in": [], "reason": "r",
            "passes": [{"verdict": "supported", "cited": [{"text": cited_text, "url": "u", "tier": "company", "source": "S1"}], "model": "m1"},
                       {"verdict": "supported", "cited": [], "model": "m2"}],
            "sources": ["u"]}


def test_summary_numbers_must_trace():
    findings = [_finding("F1", "partially_verified", "USD 1 billion in client assets"),
                _finding("F2", "unverified", "over 200,000 clients")]
    ok = report.check_section("The company says it has USD 1 billion in client assets.", findings)
    assert ok == []
    bad = report.check_section("It has over 200,000 clients.", findings)
    assert any("200,000" in p for p in bad)


def test_render_marks_draft_and_approved():
    findings = [_finding("F1", "verified", "Licensed by ADGM FSRA on 20 February 2020")]
    gaps = [{"title": "t", "what_is_missing": "m", "why_it_matters": "w", "evidence": ["F1"], "fix": "f"}] * 3
    state = {"id": "r1", "input_url": "https://www.linkedin.com/in/x", "models": {"primary": "a", "second_opinion": "b"}}
    identity = {"full_name": "X", "role": "CEO", "company": "Co", "location": "UAE"}
    md = report.render(state, identity, [], findings, gaps, "summary", [])
    assert "DRAFT" in md and "—" not in md
    state["approval"] = {"by": "Reviewer", "note": "checked sources", "at": "2026-01-01T00:00:00+00:00"}
    md = report.render(state, identity, [], findings, gaps, "summary", [])
    assert "APPROVED by Reviewer" in md
