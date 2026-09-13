"""Stage 4: two independent verification passes per claim, then a deterministic verdict."""
from __future__ import annotations

import math
import re
from collections import Counter

from .fetch import read_snapshot
from .util import tokenize, number_keys, normalize_number, find_numbers

# ---------- lexical excerpt retrieval ----------

WINDOW = 70   # words per passage
STRIDE = 35


def split_passages(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    out = []
    for start in range(0, max(1, len(words) - STRIDE), STRIDE):
        chunk = words[start:start + WINDOW]
        out.append(" ".join(chunk))
        if start + WINDOW >= len(words):
            break
    return out


class Corpus:
    """All fetched sources cut into passages, with document frequencies for idf weighting."""

    def __init__(self, sources: list[dict]):
        self.passages: list[dict] = []
        for src in sources:
            if src["status"] != "ok":
                continue
            text = read_snapshot(src["snapshot"])
            for j, p in enumerate(split_passages(text)):
                toks = tokenize(p)
                self.passages.append({"source": src["id"], "url": src["url"], "tier": src["tier"], "idx": j,
                                      "text": p, "tokens": set(toks), "numbers": number_keys(p),
                                      "bigrams": set(zip(toks, toks[1:]))})
        df: Counter = Counter()
        for p in self.passages:
            df.update(p["tokens"])
        n = max(1, len(self.passages))
        self.idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}

    def retrieve(self, query: str, k: int = 6, origin: str | None = None) -> list[dict]:
        """Top k passages by idf weighted term overlap, plus a bonus for exact numbers and for
        adjacent word pairs from the query. If origin is given, the best passage from that source
        is always included, because the claim was read from that page in the first place."""
        q_list = tokenize(query)
        q_tokens = set(q_list)
        q_bigrams = {(a, b) for a, b in zip(q_list, q_list[1:])}
        q_numbers = number_keys(query)
        scored = []
        for p in self.passages:
            overlap = q_tokens & p["tokens"]
            if not overlap:
                continue
            score = sum(self.idf.get(t, 0.0) for t in overlap)
            score += 4.0 * len(q_numbers & p["numbers"])
            if q_bigrams:
                score += 1.5 * len(q_bigrams & p["bigrams"])
            scored.append((score, p))
        scored.sort(key=lambda s: -s[0])

        def strip(p, score):
            return {**{k2: v for k2, v in p.items() if k2 not in ("tokens", "numbers", "bigrams")}, "score": round(score, 2)}

        out, seen = [], set()
        if origin:
            for score, p in scored:
                if p["source"] == origin:
                    out.append(strip(p, score))
                    seen.add((p["source"], p["idx"]))
                    break
        for score, p in scored:
            key = (p["source"], p["idx"])
            if key in seen:
                continue
            seen.add(key)
            out.append(strip(p, score))
            if len(out) >= k:
                break
        return out


# ---------- model passes ----------

VERIFY_SYSTEM = """You are a fact checker. You are given one claim and a set of excerpts from public web pages, each labelled with its source tier:
  primary = regulator, government register, court, or the publisher of an official list
  company = the company's own website or a press release the company issued
  secondary = press coverage, blogs, aggregators
Judge the claim strictly against the excerpts. Do not use outside knowledge.
Verdict values:
  supported: an excerpt states the same fact with the same numbers, names and dates. If a different source gives a different figure for what may be the same event, the verdict is still supported when one excerpt matches exactly; put the other figure and its source in "discrepancy" so the reader sees both.
  partially_supported: an excerpt supports part of it, or the numbers or wording differ (say exactly how)
  contradicted: an excerpt states something incompatible
  not_found: the excerpts do not address it
Numbers must match exactly. "Over 150" is not "144". "Fintech 50, rank 12" is not "Top 20".
Attribution matters: if an excerpt only relays what the company or the person announced or said ("Sarwa announced", "the company says", a quote from a founder, a congratulation on a milestone the company reported), it is the company's word even when it sits on a regulator's or publisher's page. List those excerpt ids in "relayed_excerpts". A regulator's own register entry, fine, notice or decision, or a publisher's own list ranking, is the source's own finding and is not relayed.
Return JSON: {"verdict": ..., "supporting_excerpts": ["E1", "E3"], "relayed_excerpts": ["E3"], "discrepancy": string or null, "note": one sentence}
supporting_excerpts lists the excerpt ids that support or contradict, as quoted strings. relayed_excerpts lists those among them that merely relay the company's own statement."""


def _format_excerpts(excerpts: list[dict]) -> str:
    return "\n\n".join(
        f"[E{i+1}] source {e['source']} ({e['tier']}) {e['url']}\n{e['text']}" for i, e in enumerate(excerpts)
    )


def run_pass(claim: dict, excerpts: list[dict], llm) -> dict:
    if not excerpts:
        return {"verdict": "not_found", "supporting_excerpts": [], "discrepancy": None,
                "note": "no excerpt in the corpus mentions the terms of this claim", "model": llm.model,
                "excerpts": []}
    user = (
        f"Claim: {claim['text']}\nNumbers in the claim: {', '.join(claim.get('numbers') or []) or 'none'}\n"
        f"Claim first appeared in: {claim['origin_url']} ({claim['origin_tier']})\n\n"
        f"Excerpts:\n{_format_excerpts(excerpts)}"
    )
    out = llm.json(VERIFY_SYSTEM, user, max_tokens=600)
    verdict = str(out.get("verdict") or "not_found").lower()
    if verdict not in ("supported", "partially_supported", "contradicted", "not_found"):
        verdict = "not_found"
    def _ids(key):
        found = []
        for x in out.get(key) or []:
            m = re.search(r"(\d+)", str(x))
            if m and 1 <= int(m.group(1)) <= len(excerpts):
                found.append(int(m.group(1)))
        return found
    ids = _ids("supporting_excerpts")
    relayed = set(_ids("relayed_excerpts"))
    cited = []
    for i in ids:
        e = excerpts[i - 1]
        tier = e["tier"]
        if i in relayed and tier in ("primary", "secondary"):
            tier = "company"  # the page relays the company's own statement; it does not confirm it
        cited.append({"source": e["source"], "url": e["url"], "tier": tier, "page_tier": e["tier"],
                      "relayed": i in relayed, "text": e["text"]})
    return {
        "verdict": verdict,
        "discrepancy": out.get("discrepancy"),
        "note": out.get("note"),
        "model": llm.model,
        "excerpts": excerpts,
        "cited": cited,
    }


def safe_pass(claim: dict, excerpts: list[dict], llm, log, name: str) -> dict:
    """Run a pass; if the model fails even after the JSON retry, record the error on the finding
    rather than losing the whole run. The error is logged, shown in the reason and counted as a warning."""
    try:
        return run_pass(claim, excerpts, llm)
    except Exception as e:  # ModelError or transport error; recorded, not hidden
        log("verify", f"{name} failed for claim {claim.get('id')}", error=str(e)[:300])
        return {"verdict": "not_found", "discrepancy": None, "note": None, "model": llm.model,
                "excerpts": excerpts, "cited": [], "failed": f"{type(e).__name__}: {str(e)[:200]}"}


# ---------- deterministic verdict ----------

def best_tier(cited: list[dict]) -> str | None:
    order = {"primary": 0, "company": 1, "secondary": 2}
    tiers = sorted({c["tier"] for c in cited}, key=lambda t: order.get(t, 3))
    return tiers[0] if tiers else None


def combine(claim: dict, p1: dict, p2: dict) -> tuple[str, str]:
    """Return (label, reason). label is verified | partially_verified | unverified.

    verified: both passes say supported and both cite a primary source.
    partially_verified: both passes find support (full or partial) but the best source is the
      company's own word, or the passes disagree on details, or one pass is only partial.
    unverified: contradicted, not found by either pass, or supported by secondary press only."""
    v1, v2 = p1["verdict"], p2["verdict"]
    t1, t2 = best_tier(p1["cited"]), best_tier(p2["cited"])
    origin_primary = claim.get("origin_tier") == "primary"

    if "contradicted" in (v1, v2):
        which = p1 if v1 == "contradicted" else p2
        src = which["cited"][0]["url"] if which["cited"] else "a source"
        return "unverified", f"contradicted by {src}: {which.get('discrepancy') or which.get('note')}"
    if "not_found" in (v1, v2):
        missing = "pass 1" if v1 == "not_found" else "pass 2"
        if v1 == v2 == "not_found":
            missing = "both passes"
        return "unverified", (f"{missing} found no source stating this; it only appears in "
                              f"{claim['origin_url']} ({claim['origin_tier']})")
    # both passes are supported or partially_supported from here
    tiers = [t for t in (t1, t2) if t]
    if not tiers:
        return "unverified", "passes reported support but cited no excerpt"
    strongest = sorted(tiers, key=lambda t: {"primary": 0, "company": 1, "secondary": 2}[t])[0]
    if v1 == v2 == "supported" and t1 == "primary" and t2 == "primary":
        return "verified", "both passes matched a primary source"
    if strongest == "primary":
        detail = p1.get("discrepancy") or p2.get("discrepancy") or "one pass found only partial support"
        return "partially_verified", f"primary source found but details differ: {detail}"
    if strongest == "company":
        detail = ""
        if "partially_supported" in (v1, v2):
            detail = " and details differ: " + str(p1.get("discrepancy") or p2.get("discrepancy") or "")
        relayed_pages = sorted({c["url"] for p in (p1, p2) for c in p["cited"] if c.get("relayed")})
        where = "stated only by the company itself (own site or issued release)"
        if relayed_pages:
            where += "; " + relayed_pages[0] + " repeats the company's announcement rather than confirming it"
        return "partially_verified", where + "; no regulator or independent primary source confirms it" + detail
    # secondary only
    if origin_primary:
        return "partially_verified", "primary origin but the passes only matched press restatements"
    return "unverified", "only repeated by secondary press; no primary or company source found"


def verify_claims(claims: list[dict], sources: list[dict], llm_primary, llm_second, log) -> list[dict]:
    corpus = Corpus(sources)
    log("verify", f"corpus: {len(corpus.passages)} passages from {sum(1 for s in sources if s['status']=='ok')} sources")
    findings = []
    for i, claim in enumerate(claims, start=1):
        # Pass 1: full claim text as the query.
        ex1 = corpus.retrieve(claim["text"] + " " + " ".join(claim.get("numbers") or []), k=6, origin=claim["origin"])
        p1 = safe_pass(claim, ex1, llm_primary, log, "pass 1")
        # Pass 2: independent query built from the quote plus numbers, different model, more excerpts.
        q2 = (claim.get("quote") or claim["text"]) + " " + " ".join(claim.get("numbers") or [])
        ex2 = corpus.retrieve(q2, k=8, origin=claim["origin"])
        p2 = safe_pass(claim, ex2, llm_second, log, "pass 2")
        if p1.get("failed") or p2.get("failed"):
            which = "pass 1" if p1.get("failed") else "pass 2"
            label, reason = "unverified", f"{which} failed twice with a model error, so the claim could not be checked: " + \
                (p1.get("failed") or p2.get("failed"))
        else:
            label, reason = combine(claim, p1, p2)
        finding = {
            "id": f"F{i}",
            "claim_id": claim["id"],
            "claim": claim["text"],
            "quote": claim.get("quote"),
            "category": claim["category"],
            "about": claim["about"],
            "numbers": claim.get("numbers") or [],
            "origin_url": claim["origin_url"],
            "origin_tier": claim["origin_tier"],
            "also_in": claim.get("also_in") or [],
            "label": label,
            "reason": reason,
            "passes": [
                {k: v for k, v in p.items() if k != "excerpts"} for p in (p1, p2)
            ],
            "sources": sorted({c["url"] for p in (p1, p2) for c in p["cited"]}),
        }
        findings.append(finding)
        log("verify", f"{finding['id']} {label}: {claim['text'][:90]}",
            pass1=p1["verdict"], pass2=p2["verdict"], reason=reason)
    return findings
