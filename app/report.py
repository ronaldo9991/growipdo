"""Stage 6: write the one page diagnostic. Summary and gaps must pass the house rules."""
from __future__ import annotations

from . import lint
from .util import now_iso

SUMMARY_SYSTEM = """Write the summary paragraph of a one page diagnostic about how a founder shows up publicly.
120 to 170 words, plain English, one paragraph, no bullet points, no headings.
Use only the verified and partially verified findings given. Say which numbers are only the company's own word.
Every number you write must appear verbatim in one of the findings given. Do not round, convert or add numbers.
No em dashes. No hashtags. No filler words such as leverage, robust, journey, landscape, navigate, empower, unlock, seamless, testament, pivotal, delve, innovative, crucial."""


def allowed_texts(findings: list[dict]) -> list[str]:
    """Text a number may trace to: claim text and cited excerpts of verified or partially verified findings."""
    out = []
    for f in findings:
        if f["label"] in ("verified", "partially_verified"):
            out.append(f["claim"])
            out.append(f.get("quote") or "")
            for p in f["passes"]:
                for c in p.get("cited") or []:
                    out.append(c["text"])
    return out


def check_section(text: str, findings: list[dict]) -> list[str]:
    problems = [str(i) for i in lint.lint_text(text)]
    for n in lint.untraced_numbers(text, allowed_texts(findings)):
        problems.append(f"number {n!r} does not trace to a verified or partially verified finding")
    return problems


def write_summary(identity: dict, findings: list[dict], llm, log) -> tuple[str, list[str]]:
    usable = [f for f in findings if f["label"] in ("verified", "partially_verified")]
    refused = [f for f in findings if f["label"] == "unverified"]
    body = "\n".join(f"{f['id']} [{f['label']}] {f['claim']} (reason: {f['reason']})" for f in usable)
    refused_body = "\n".join(f"{f['id']} {f['claim']}" for f in refused)
    user = (
        f"Subject: {identity['full_name']}, {identity.get('role')}, {identity.get('company')}\n\n"
        f"Usable findings:\n{body or '(none)'}\n\nRefused findings (mention that these could not be verified, "
        f"without their numbers):\n{refused_body or '(none)'}\n\nWrite the summary."
    )
    text = llm.text(SUMMARY_SYSTEM, user, max_tokens=700).strip()
    problems = check_section(text, findings)
    if problems:
        log("report", "summary failed house rules, asking for a rewrite", problems=problems)
        text = llm.text(SUMMARY_SYSTEM, user + "\n\nYour previous draft broke these rules, fix every one:\n- "
                        + "\n- ".join(problems) + "\n\nPrevious draft:\n" + text, max_tokens=700).strip()
        problems = check_section(text, findings)
    if problems:
        text = lint.mechanical_fix(text)
        problems = check_section(text, findings)
    return text, problems


def gap_text(g: dict) -> str:
    return f"{g['title']}\n{g['what_is_missing']} {g['why_it_matters']} Fix: {g['fix']}"


def check_gaps(gaps: list[dict], findings: list[dict]) -> list[str]:
    problems = []
    for i, g in enumerate(gaps, start=1):
        for p in check_section(gap_text(g), findings):
            problems.append(f"gap {i}: {p}")
    return problems


def render(run_state: dict, identity: dict, sources: list[dict], findings: list[dict], gaps: list[dict],
           summary: str, lint_notes: list[str]) -> str:
    verified = [f for f in findings if f["label"] == "verified"]
    partial = [f for f in findings if f["label"] == "partially_verified"]
    refused = [f for f in findings if f["label"] == "unverified"]
    src_by_url = {s["url"]: s for s in sources}
    approval = run_state.get("approval")
    lines = []
    lines.append(f"# Prospect diagnostic: {identity['full_name']}")
    lines.append("")
    lines.append(f"{identity.get('role')}, {identity.get('company')}, {identity.get('location')}")
    lines.append("")
    if approval:
        lines.append(f"Status: APPROVED by {approval['by']} on {approval['at']}")
        lines.append(f"Approver note: {approval['note']}")
    else:
        lines.append("Status: DRAFT, not approved. A human must review and approve before this leaves the building.")
    lines.append("")
    lines.append(f"Run {run_state['id']}, generated {now_iso()}. Input: {run_state.get('input_url')} (never fetched). "
                 f"Models: {run_state.get('models', {}).get('primary')} (pass 1), "
                 f"{run_state.get('models', {}).get('second_opinion')} (pass 2, gaps).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary)
    lines.append("")
    lines.append(f"Findings: {len(verified)} verified, {len(partial)} partially verified, {len(refused)} refused.")
    lines.append("")
    lines.append("## Three biggest gaps")
    lines.append("")
    for i, g in enumerate(gaps, start=1):
        lines.append(f"{i}. {g['title']}")
        lines.append(f"   {g['what_is_missing']} {g['why_it_matters']}")
        lines.append(f"   Fix: {g['fix']} Evidence: {', '.join(g['evidence'])}.")
        lines.append("")

    def block(title, items, show_reason):
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("None.")
            lines.append("")
            return
        for f in items:
            lines.append(f"- {f['id']}. {f['claim']}")
            srcs = f["sources"] or [f["origin_url"]]
            for u in srcs[:3]:
                tier = src_by_url.get(u, {}).get("tier", f["origin_tier"] if u == f["origin_url"] else "")
                lines.append(f"  Source: {u}" + (f" ({tier})" if tier else ""))
            p1, p2 = f["passes"]
            lines.append(f"  Pass 1 ({p1['model']}): {p1['verdict']}. Pass 2 ({p2['model']}): {p2['verdict']}.")
            if show_reason or f["label"] != "verified":
                lines.append(f"  Why: {f['reason']}")
            lines.append("")

    block("Verified", verified, False)
    block("Partially verified", partial, True)
    block("Refused", refused, True)

    bad = [s for s in sources if s["status"] != "ok"]
    lines.append(f"## Could not check ({len(bad)})")
    lines.append("")
    for s in bad:
        lines.append(f"- {s['url']}: {s['error'] or s['status']}")
    if not bad:
        lines.append("Every fetched source returned readable text.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    ok = [s for s in sources if s["status"] == "ok"]
    lines.append(
        f"The LinkedIn URL was used only to derive a name; LinkedIn itself was never fetched. "
        f"{len(sources)} public pages were searched and fetched ({len(ok)} readable), each saved under evidence/. "
        f"Every claim was checked twice, by two different models over independently retrieved excerpts, and the label "
        f"was set by fixed rules: verified needs both passes to match a primary source (regulator, official register, "
        f"official list); partially verified means the only support is the company's own word or the details differ; "
        f"refused means contradicted, not found, or repeated only by press. "
        f"Numbers in the Summary and Gaps sections are checked mechanically against the verified and partially verified findings."
    )
    lines.append("")
    if lint_notes:
        lines.append("## House rules warnings")
        lines.append("")
        for n in lint_notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)
