from app.claims import dedupe_claims


def _c(text, tier, cat="funding", numbers=None, url=None):
    return {"text": text, "quote": text, "category": cat, "about": "company", "numbers": numbers or [],
            "origin": "S", "origin_url": url or f"https://{tier}.example/{abs(hash(text))}", "origin_tier": tier}


def test_dedupe_merges_syndicated_claims():
    claims = [
        _c("Sarwa raised USD 15 million in a Series B round led by Mubadala", "secondary", numbers=["USD 15 million"]),
        _c("Sarwa raised a USD 15 million Series B led by Mubadala Investment Company", "company", numbers=["USD 15 million"]),
        _c("Sarwa was founded in 2017", "primary", "founding", ["2017"]),
    ]
    out = dedupe_claims(claims, lambda *a, **k: None)
    assert len(out) == 2
    merged = [c for c in out if "15 million" in c["text"]][0]
    assert merged["origin_tier"] == "company"
    assert len(merged["also_in"]) == 1


def test_selection_round_robins_across_sources(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_CLAIMS_PER_SOURCE_SELECTED", 2)
    claims = []
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
    for i, w in enumerate(words):
        c = _c(f"{w} permission granted {i}", "primary", "regulatory", [str(i)], url="https://reg.example/x")
        c["origin"] = "S1"; claims.append(c)
    for i, w in enumerate(["ranked twelfth on the list", "founded in 2017 by three people", "headquartered in the UAE"]):
        c = _c(f"Forbes says the company is {w}", "primary", "award", [], url="https://forbes.example/y")
        c["origin"] = "S2"; claims.append(c)
    out = dedupe_claims(claims, lambda *a, **k: None, cap=6)
    assert sum(1 for c in out if c["origin"] == "S2") == 2
    assert len(out) == 6


def test_quote_must_be_in_page():
    from app.claims import quote_in_page, _norm
    page = _norm("The DFSA has fined Sarwa Digital Wealth Limited USD 191,100 for making a public offer.\nMore text here.")
    assert quote_in_page("The DFSA has fined Sarwa Digital Wealth Limited USD 191,100", page)
    assert not quote_in_page("Sarwa was included in the Forbes 2026 Fintech 50 list", page)
