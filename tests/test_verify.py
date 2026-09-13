from app import config
from app.verify import Corpus, combine, split_passages


def _sources(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    dfsa = tmp_path / "dfsa.txt"
    dfsa.write_text("url: x\n---\n" + "Filler text about markets. " * 30 +
                    "The DFSA has fined Sarwa Digital Wealth Limited USD 191,100 for making a public offer of shares "
                    "without an approved prospectus. The email was sent to almost 100,000 users and over 150 potential "
                    "investors committed about USD 2 million. " + "More filler about other things. " * 30)
    press = tmp_path / "press.txt"
    press.write_text("url: y\n---\n" + "Sarwa said 144 investors put in USD 2.1 million. " + "Other text. " * 40)
    return [
        {"id": "S1", "url": "https://www.dfsa.ae/news/x", "tier": "primary", "status": "ok", "snapshot": str(dfsa)},
        {"id": "S2", "url": "https://international-adviser.com/x", "tier": "secondary", "status": "ok", "snapshot": str(press)},
        {"id": "S3", "url": "https://blocked", "tier": "secondary", "status": "could_not_check", "snapshot": ""},
    ]


def test_retrieval_finds_passage_with_number(tmp_path, monkeypatch):
    corpus = Corpus(_sources(tmp_path, monkeypatch))
    hits = corpus.retrieve("DFSA fined Sarwa USD 191,100 for a public offer without a prospectus", k=3)
    assert hits and hits[0]["source"] == "S1"
    assert "191,100" in hits[0]["text"]


def test_retrieval_number_variant(tmp_path, monkeypatch):
    corpus = Corpus(_sources(tmp_path, monkeypatch))
    hits = corpus.retrieve("fine of $191100", k=3)
    assert hits and "191,100" in hits[0]["text"]


def test_split_passages_overlap():
    words = " ".join(f"w{i}" for i in range(200))
    ps = split_passages(words)
    assert len(ps) > 3 and "w100" in " ".join(ps)


def _pass(verdict, tier=None, discrepancy=None):
    cited = [{"source": "S", "url": "u", "tier": tier, "text": "t"}] if tier else []
    return {"verdict": verdict, "cited": cited, "discrepancy": discrepancy, "note": "n"}


CLAIM = {"origin_url": "https://x", "origin_tier": "company"}


def test_verified_needs_two_primary_supports():
    assert combine(CLAIM, _pass("supported", "primary"), _pass("supported", "primary"))[0] == "verified"
    assert combine(CLAIM, _pass("supported", "primary"), _pass("supported", "company"))[0] == "partially_verified"


def test_company_only_is_partial():
    label, reason = combine(CLAIM, _pass("supported", "company"), _pass("supported", "company"))
    assert label == "partially_verified"
    assert "company" in reason


def test_secondary_only_is_refused():
    assert combine(CLAIM, _pass("supported", "secondary"), _pass("supported", "secondary"))[0] == "unverified"


def test_contradiction_is_refused():
    label, reason = combine(CLAIM, _pass("supported", "secondary"), _pass("contradicted", "primary", "says over 150 not 144"))
    assert label == "unverified" and "150" in reason


def test_not_found_is_refused():
    assert combine(CLAIM, _pass("supported", "primary"), _pass("not_found"))[0] == "unverified"


def test_partial_with_primary():
    label, _ = combine(CLAIM, _pass("partially_supported", "primary", "rank 12 on a 50 list"), _pass("supported", "primary"))
    assert label == "partially_verified"


def test_relayed_primary_counts_as_company():
    p1 = {"verdict": "supported", "cited": [{"source": "S", "url": "https://www.adgm.com/media/announcements/x", "tier": "company", "relayed": True, "text": "t"}], "discrepancy": None, "note": "n"}
    p2 = _pass("supported", "company")
    label, reason = combine(CLAIM, p1, p2)
    assert label == "partially_verified" and "repeats the company's announcement" in reason


def test_origin_passage_always_included(tmp_path, monkeypatch):
    corpus = Corpus(_sources(tmp_path, monkeypatch))
    # A query that lexically favours the DFSA page still brings the origin's best passage.
    hits = corpus.retrieve("DFSA fined Sarwa USD 191,100 public offer prospectus", k=2, origin="S2")
    assert hits[0]["source"] == "S2"
    assert any(h["source"] == "S1" for h in hits)


def test_list_page_profile_data_is_company_word(tmp_path, monkeypatch):
    from app.verify import run_pass
    monkeypatch.setattr(config, "ROOT", tmp_path)
    ex = [{"source": "S9", "url": "https://www.forbesmiddleeast.com/lists/fintech-50/sarwa/", "tier": "primary", "idx": 0,
           "list_page": True, "text": "12. Sarwa. Date of Establishment: 2017. Sarwa hit its first profit in Q1 2024."}]

    class FakeLLM:
        model = "fake"
        def json(self, system, user, max_tokens=0):
            return {"verdict": "supported", "supporting_excerpts": ["E1"], "relayed_excerpts": [], "discrepancy": None, "note": "n"}

    rank = run_pass({"text": "Sarwa is ranked 12", "origin_url": "u", "origin_tier": "primary", "category": "award", "numbers": ["12"]}, ex, FakeLLM())
    assert rank["cited"][0]["tier"] == "primary"
    profit = run_pass({"text": "Sarwa was profitable in Q1 2024", "origin_url": "u", "origin_tier": "primary", "category": "traction", "numbers": []}, ex, FakeLLM())
    assert profit["cited"][0]["tier"] == "company" and profit["cited"][0]["relayed"]
