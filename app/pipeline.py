"""Orchestrates the stages for one run. Any exception marks the run failed with the traceback in the log."""
from __future__ import annotations

from . import config, report
from .claims import extract_claims, dedupe_claims
from .gaps import find_gaps
from .identify import identify, slug_from_linkedin
from .ledger import Run
from .llm import LLM
from .research import research
from . import search as search_mod
from .search import search as web_search
from .verify import verify_claims


def build_llms(run: Run):
    primary = config.require("MODEL_PRIMARY")
    second = config.require("MODEL_SECOND_OPINION")
    if primary == second:
        raise RuntimeError("MODEL_PRIMARY and MODEL_SECOND_OPINION must be two different models")
    run.state["models"] = {"primary": primary, "second_opinion": second}
    return LLM(primary, log=run.log), LLM(second, log=run.log)


def run_pipeline(run: Run) -> Run:
    try:
        if search_mod.provider() != "duckduckgo":
            config.require({"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY", "serper": "SERPER_API_KEY"}.get(search_mod.provider(), "TAVILY_API_KEY"))
        llm1, llm2 = build_llms(run)
        url = run.state["input_url"]

        run.set_stage("identify")
        slug = slug_from_linkedin(url)
        identity = identify(slug, web_search, llm1, run.log)
        run.state["subject"] = identity
        run.save()
        run.log("identify", f"{identity['full_name']}, {identity.get('role')} at {identity.get('company')}",
                confidence=identity["confidence"], reasoning=identity.get("reasoning"))

        run.set_stage("research")
        sources = research(identity, run.id, web_search, run.log)
        run.ledger["sources"] = sources
        run.save()

        run.set_stage("claims")
        raw = extract_claims(identity, sources, llm1, run.log)
        claims = dedupe_claims(raw, run.log)
        run.ledger["claims"] = claims
        run.save()
        if not claims:
            raise RuntimeError("no claims extracted from any source")

        run.set_stage("verify")
        findings = verify_claims(claims, sources, llm1, llm2, run.log)
        run.ledger["findings"] = findings
        run.state["counts"] = {
            "verified": sum(1 for f in findings if f["label"] == "verified"),
            "partially_verified": sum(1 for f in findings if f["label"] == "partially_verified"),
            "unverified": sum(1 for f in findings if f["label"] == "unverified"),
        }
        run.save()

        run.set_stage("gaps")
        gaps = find_gaps(identity, findings, sources, llm2, run.log)
        problems = report.check_gaps(gaps, findings)
        if problems:
            run.log("gaps", "gaps failed house rules, asking for a rewrite", problems=problems)
            gaps = find_gaps(identity, findings, sources, llm2, run.log)
            problems = report.check_gaps(gaps, findings)
        if problems:
            for g in gaps:
                for k in ("title", "what_is_missing", "why_it_matters", "fix"):
                    g[k] = report.lint.mechanical_fix(g[k])
            problems = report.check_gaps(gaps, findings)
        run.ledger["gaps"] = gaps
        run.save()

        run.set_stage("report")
        summary, summary_problems = report.write_summary(identity, findings, llm1, run.log)
        lint_notes = [f"summary: {p}" for p in summary_problems] + problems
        run.ledger["summary"] = summary
        run.ledger["lint"] = lint_notes
        write_diagnostic(run)
        run.state["status"] = "draft"
        run.state["stage"] = "human_gate"
        run.save()
        run.log("human_gate", "draft ready, waiting for a human to approve or reject", lint_warnings=len(lint_notes))
    except Exception as exc:
        run.fail(exc)
        raise
    return run


def write_diagnostic(run: Run) -> str:
    md = report.render(run.state, run.state["subject"], run.ledger["sources"], run.ledger["findings"],
                       run.ledger["gaps"], run.ledger["summary"], run.ledger.get("lint") or [])
    run.diagnostic_path.write_text(md, encoding="utf-8")
    return md


def approve(run: Run, by: str, note: str) -> Run:
    if run.state["status"] != "draft":
        raise RuntimeError(f"run is {run.state['status']}, only a draft can be approved")
    if not by.strip() or len(note.strip()) < 10:
        raise RuntimeError("approval needs a name and a note of at least 10 characters saying what was checked")
    from .util import now_iso
    run.state["approval"] = {"by": by.strip(), "note": note.strip(), "at": now_iso()}
    run.state["status"] = "approved"
    run.save()
    write_diagnostic(run)
    run.log("human_gate", f"approved by {by.strip()}", note=note.strip())
    return run


def reject(run: Run, by: str, note: str) -> Run:
    if run.state["status"] != "draft":
        raise RuntimeError(f"run is {run.state['status']}, only a draft can be rejected")
    from .util import now_iso
    run.state["approval"] = None
    run.state["rejection"] = {"by": by.strip(), "note": note.strip(), "at": now_iso()}
    run.state["status"] = "rejected"
    run.save()
    run.log("human_gate", f"rejected by {by.strip()}", note=note.strip())
    return run
