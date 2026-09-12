"""Stage 2: search the public web, fetch pages, snapshot them, classify each source."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from . import config
from .fetch import fetch
from .util import host_of


def classify_source(url: str, company_domains: list[str]) -> str:
    """primary: regulators, official registers and the publisher of an official list.
    company: the company's own site or a wire release the company issued.
    secondary: everything else (press, blogs, aggregators)."""
    host = host_of(url)
    path = url.lower()
    for p in config.PRIMARY_HOSTS:
        if "/" in p:
            h, _, prefix = p.partition("/")
            if (host == h or host.endswith("." + h)) and ("/" + prefix) in path:
                return "primary"
        elif host == p or host.endswith("." + p):
            return "primary"
    for d in company_domains:
        if host == d or host.endswith("." + d):
            return "company"
    for w in config.WIRE_HOSTS:
        if "/" in w:
            h, _, prefix = w.partition("/")
            if (host == h or host.endswith("." + h)) and ("/" + prefix) in path:
                return "company"
        elif host == w or host.endswith("." + w):
            return "company"
    return "secondary"


def query_plan(identity: dict) -> list[str]:
    name = identity["full_name"]
    company = identity.get("company") or ""
    plan = [
        f"{company} ADGM FSRA financial services permission register",
        f"{company} DFSA decision notice",
        f"{company} regulator fine penalty",
        f"{company} regulatory action",
        f"{company} press release funding round",
        f"{company} Series B Mubadala",
        f"{company} Forbes Middle East fintech list",
        f"{company} assets under management clients users",
        f"{company} profitable revenue",
        f"{name} {company} co-founder CEO interview",
        f"{name} {company} founded",
        f'"{name}" fintech',
    ]
    return [q for q in plan if q.strip()]


def research(identity: dict, run_id: str, search, log, max_sources: int = config.MAX_SOURCES) -> list[dict]:
    company_domains = identity.get("company_domains") or []
    candidates: dict[str, dict] = {}
    for q in query_plan(identity):
        try:
            results = search(q, max_results=6)
        except Exception as e:  # a single bad query should not kill research
            log("research", f"search failed: {q!r}", error=str(e))
            continue
        log("research", f"{len(results)} results: {q!r}")
        for r in results:
            url = r["url"].split("#")[0]
            if url not in candidates:
                candidates[url] = {"url": url, "title": r["title"], "snippet": r["snippet"], "queries": [q]}
            else:
                candidates[url]["queries"].append(q)
    for u in identity.get("evidence_urls") or []:
        candidates.setdefault(u, {"url": u, "title": "", "snippet": "", "queries": ["identify"]})
    if not candidates:
        raise RuntimeError("research found no candidate sources")

    # Rank: primary first, then company, then by how many queries hit it.
    order = {"primary": 0, "company": 1, "secondary": 2}
    ranked = sorted(
        candidates.values(),
        key=lambda c: (order[classify_source(c["url"], company_domains)], -len(c["queries"])),
    )[:max_sources]
    log("research", f"fetching {len(ranked)} of {len(candidates)} candidate urls")

    client = httpx.Client(follow_redirects=True, timeout=config.FETCH_TIMEOUT,
                          headers={"User-Agent": config.USER_AGENT,
                                   "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                   "Accept-Language": "en-US,en;q=0.9"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(lambda c: fetch(c["url"], run_id, client), ranked))
    client.close()

    sources = []
    for i, (cand, res) in enumerate(zip(ranked, fetched), start=1):
        tier = classify_source(cand["url"], company_domains)
        src = {
            "id": f"S{i}",
            "url": cand["url"],
            "final_url": res.final_url,
            "title": res.title or cand["title"],
            "tier": tier,
            "status": res.status,
            "http_status": res.http_status,
            "error": res.error,
            "snapshot": res.snapshot,
            "chars": len(res.text),
            "queries": cand["queries"],
        }
        sources.append(src)
        log("research", f"{src['id']} {res.status} {tier} {cand['url']}",
            http_status=res.http_status, chars=len(res.text), error=res.error or None)
    ok = sum(1 for s in sources if s["status"] == "ok")
    if ok == 0:
        raise RuntimeError("no source could be fetched; nothing to verify against")
    return sources
