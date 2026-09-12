"""Stage 5: the three biggest gaps in how the subject shows up publicly."""
from __future__ import annotations

GAPS_SYSTEM = """You advise founders on how they show up in public. You are given a ledger of fact checked findings about a founder and their company.
Name the three biggest gaps in how this person shows up publicly. A gap is something a serious counterparty (an investor, a regulator, a journalist, an enterprise client) would notice is missing, unaddressed or inconsistent when they research this person.
Weigh these things:
- Regulatory or legal records that the founder's own narrative does not address.
- Headline numbers that only the company itself states, with no independent confirmation.
- Claims that failed verification or that differ between sources.
- Awards or list placements described more generously than the source supports.
- Things the public record says nothing about at all.
Rules:
- Use only the findings given. Every number you write must appear in a finding labelled verified or partially_verified. If a number is only in a refused finding, describe it without the number.
- Cite finding ids in "evidence".
- Plain English. No em dashes. No hashtags. No words like leverage, robust, journey, landscape, navigate, empower, unlock, seamless, testament, pivotal, delve.
Return JSON: {"gaps": [{"title": short, "what_is_missing": 2 to 3 sentences, "why_it_matters": 1 to 2 sentences, "evidence": [finding ids], "fix": one sentence}]} with exactly three gaps, most important first."""


def format_findings(findings: list[dict]) -> str:
    lines = []
    for f in findings:
        srcs = ", ".join(f["sources"][:2]) or f["origin_url"]
        lines.append(f"{f['id']} [{f['label']}] ({f['category']}) {f['claim']}\n    reason: {f['reason']}\n    sources: {srcs}")
    return "\n".join(lines)


def find_gaps(identity: dict, findings: list[dict], sources: list[dict], llm, log) -> list[dict]:
    unreachable = [s for s in sources if s["status"] != "ok"]
    user = (
        f"Subject: {identity['full_name']}, {identity.get('role')}, {identity.get('company')}, {identity.get('location')}\n\n"
        f"Findings:\n{format_findings(findings)}\n\n"
        f"Sources that could not be checked: {', '.join(s['url'] + ' (' + (s['error'] or s['status']) + ')' for s in unreachable) or 'none'}\n\n"
        "Name the three biggest gaps."
    )
    out = llm.json(GAPS_SYSTEM, user, max_tokens=1500)
    gaps = out.get("gaps") if isinstance(out, dict) else out
    if not isinstance(gaps, list) or len(gaps) < 3:
        raise RuntimeError(f"gap stage returned {len(gaps) if isinstance(gaps, list) else 'no'} gaps, need three")
    valid_ids = {f["id"] for f in findings}
    cleaned = []
    for g in gaps[:3]:
        ev = [e for e in (g.get("evidence") or []) if e in valid_ids]
        if not ev:
            raise RuntimeError(f"gap {g.get('title')!r} cites no valid finding id")
        cleaned.append({"title": g.get("title", "").strip(), "what_is_missing": g.get("what_is_missing", "").strip(),
                        "why_it_matters": g.get("why_it_matters", "").strip(), "evidence": ev,
                        "fix": g.get("fix", "").strip()})
    log("gaps", "three gaps named", titles=[g["title"] for g in cleaned])
    return cleaned
