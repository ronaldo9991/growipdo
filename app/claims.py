"""Stage 3: pull atomic factual claims out of each fetched source, then dedupe them."""
from __future__ import annotations

from . import config
from .fetch import read_snapshot
from .util import tokenize, number_keys

EXTRACT_SYSTEM = """You extract atomic, checkable factual claims about a named person and their company from one web page.
Rules:
- One fact per claim. Split compound sentences.
- Keep every number, currency, date and rank exactly as written in the page.
- Quote the sentence the claim comes from, verbatim, in "quote".
- Only claims about the subject person or the subject company. Ignore claims about other companies, generic market statistics, and page boilerplate.
- Prefer claims that a reviewer would want checked: regulatory status, licences, fines, funding amounts, investors, client or user counts, assets, revenue or profit, awards and list rankings, "first" or "largest" claims, founding date, founders and roles.
- Do not invent. If the page has nothing relevant, return an empty list.
Return JSON: {"claims": [{"text": string, "quote": string, "category": one of regulatory|funding|traction|award|role|founding|other, "about": "person"|"company", "numbers": [strings as written]}]}"""


def extract_claims(identity: dict, sources: list[dict], llm, log,
                   per_source: int = config.MAX_CLAIMS_PER_SOURCE) -> list[dict]:
    name = identity["full_name"]
    company = identity.get("company") or ""
    claims: list[dict] = []
    for src in sources:
        if src["status"] != "ok":
            continue
        text = read_snapshot(src["snapshot"])[:14000]
        user = (
            f"Subject person: {name}\nSubject company: {company}\nSource URL: {src['url']}\n"
            f"Source tier: {src['tier']}\n\nPage text:\n{text}\n\nExtract at most {per_source} claims."
        )
        try:
            out = llm.json(EXTRACT_SYSTEM, user, max_tokens=3000)
        except Exception as e:
            log("claims", f"extraction failed for {src['id']}", error=str(e))
            raise
        items = out.get("claims") if isinstance(out, dict) else out
        n = 0
        for item in items or []:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            claims.append(
                {
                    "text": item["text"].strip(),
                    "quote": (item.get("quote") or "").strip(),
                    "category": item.get("category") or "other",
                    "about": item.get("about") or "company",
                    "numbers": [str(x) for x in item.get("numbers") or []],
                    "origin": src["id"],
                    "origin_url": src["url"],
                    "origin_tier": src["tier"],
                }
            )
            n += 1
            if n >= per_source:
                break
        log("claims", f"{n} claims from {src['id']} ({src['tier']})")
    return claims


def _similar(a: dict, b: dict) -> bool:
    ta, tb = set(tokenize(a["text"])), set(tokenize(b["text"]))
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    na, nb = number_keys(a["text"]), number_keys(b["text"])
    same_numbers = bool(na) and na == nb and a["category"] == b["category"]
    return jaccard >= 0.6 or (same_numbers and jaccard >= 0.35)


def dedupe_claims(claims: list[dict], log, cap: int = config.MAX_CLAIMS_TOTAL) -> list[dict]:
    """Merge near duplicate claims (press syndication). Keep the origin from the best tier."""
    order = {"primary": 0, "company": 1, "secondary": 2}
    merged: list[dict] = []
    for c in sorted(claims, key=lambda c: order.get(c["origin_tier"], 3)):
        for m in merged:
            if _similar(m, c):
                m.setdefault("also_in", [])
                if c["origin_url"] not in m["also_in"] and c["origin_url"] != m["origin_url"]:
                    m["also_in"].append(c["origin_url"])
                break
        else:
            c.setdefault("also_in", [])
            merged.append(c)
    # Prefer a spread: regulatory and numeric claims first, then the rest.
    def prio(c):
        return (0 if c["category"] == "regulatory" else 1, 0 if c["numbers"] else 1, order.get(c["origin_tier"], 3))
    merged.sort(key=prio)
    for i, c in enumerate(merged, start=1):
        c["id"] = f"C{i}"
    log("claims", f"{len(claims)} raw claims, {len(merged)} after dedupe, keeping {min(len(merged), cap)}")
    return merged[:cap]
