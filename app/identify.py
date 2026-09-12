"""Stage 1: resolve a LinkedIn URL to a named person using the public web only."""
from __future__ import annotations

import re
from urllib.parse import urlparse


class IdentifyError(RuntimeError):
    pass


def slug_from_linkedin(url: str) -> str:
    """Return the /in/<slug> part of a LinkedIn profile URL. Nothing is fetched."""
    u = (url or "").strip()
    if not re.match(r"^https?://", u, re.IGNORECASE):
        u = "https://" + u
    parsed = urlparse(u)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise IdentifyError(f"not a LinkedIn URL: {url}")
    m = re.match(r"^/in/([^/?#]+)/?", parsed.path)
    if not m:
        raise IdentifyError(f"not a LinkedIn profile URL (expected /in/<slug>): {url}")
    return m.group(1).lower()


def name_guesses(slug: str) -> list[str]:
    """Plausible spellings of the person's name from the slug. The web resolves the rest."""
    base = re.sub(r"[-_]?\d+[a-z0-9]*$", "", slug)
    guesses = []
    if "-" in base:
        guesses.append(" ".join(p.capitalize() for p in base.split("-") if p))
    guesses.append(base)
    return [g for g in guesses if g]


IDENTIFY_SYSTEM = """You resolve a LinkedIn profile slug to a real, named person using only the web search snippets given.
You must not guess beyond the evidence. If the snippets do not clearly point to one person, say so with low confidence.
Return JSON with keys:
  full_name (string), company (string), role (string), location (string),
  company_domains (list of website hosts belonging to the company, e.g. ["sarwa.co"]),
  confidence (number 0 to 1), reasoning (one sentence), evidence_urls (list of urls from the snippets that support this)."""


def identify(slug: str, search, llm, log) -> dict:
    queries = []
    for g in name_guesses(slug):
        queries.append(f"{g} founder")
        queries.append(f"{g} CEO company UAE")
    seen = set()
    results = []
    for q in queries:
        for r in search(q, max_results=6):
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            results.append(r)
    log("identify", f"{len(results)} search results from {len(queries)} queries", queries=queries)
    if not results:
        raise IdentifyError("search returned nothing for the profile slug; cannot identify the person")
    snippets = "\n\n".join(
        f"[{i+1}] {r['title']}\nURL: {r['url']}\n{r['snippet'][:600]}" for i, r in enumerate(results[:24])
    )
    user = (
        f"LinkedIn slug: {slug}\nName guesses from the slug: {', '.join(name_guesses(slug))}\n\n"
        f"Search snippets:\n{snippets}\n\nWho is this person?"
    )
    out = llm.json(IDENTIFY_SYSTEM, user, max_tokens=800)
    if not isinstance(out, dict) or not out.get("full_name"):
        raise IdentifyError(f"model did not return a person: {out}")
    conf = float(out.get("confidence") or 0)
    if conf < 0.6:
        raise IdentifyError(
            f"low confidence ({conf:.2f}) that the slug is {out.get('full_name')}: {out.get('reasoning')}. "
            "Stopping so a human can confirm the subject."
        )
    out["confidence"] = conf
    out["slug"] = slug
    out["company_domains"] = [d.lower().replace("www.", "") for d in out.get("company_domains") or []]
    out["evidence_urls"] = [u for u in out.get("evidence_urls") or [] if u in seen]
    return out
