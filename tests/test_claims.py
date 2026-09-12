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
