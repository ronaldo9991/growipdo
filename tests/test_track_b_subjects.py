"""Regression tests for the live failure on linkedin.com/in/jayyanar: identify found the person but no
company, the company search templates collapsed into generic queries, and the pages about him were
never fetched."""
from app.pipeline import no_claims_message
from app.research import query_plan, select_candidates
from app.util import subject_keys

AJ = {"full_name": "Ayyanar Jeyakrishnan", "company": "", "role": "IT expert / technical leader", "slug": "jayyanar",
      "company_domains": [], "evidence_urls": ["https://github.com/jayyanar"]}
MARK = {"full_name": "Mark Chahwan", "company": "Sarwa", "role": "Co-founder and Group CEO", "slug": "markchahwan",
        "company_domains": ["sarwa.co"], "evidence_urls": []}


def test_no_company_means_no_company_templates():
    plan = query_plan(AJ)
    assert plan and all("Ayyanar Jeyakrishnan" in q for q in plan)
    assert not any('""' in q or q.startswith(" ") or "ADGM" in q or "site:" in q for q in plan)


def test_company_plan_keeps_company_and_person_searches():
    plan = query_plan(MARK)
    assert any(q.startswith("Sarwa ADGM FSRA") for q in plan)
    assert any(q == '"Mark Chahwan"' for q in plan)
    assert len(plan) == len(set(plan))


def test_subject_keys():
    assert subject_keys(AJ) == ["ayyanar jeyakrishnan", "jeyakrishnan", "jayyanar"]
    assert subject_keys(MARK) == ["mark chahwan", "chahwan", "markchahwan", "sarwa"]
    assert "sarwa" in subject_keys({**MARK, "company": "Sarwa Digital Wealth (Capital) Limited"})
    # a two letter surname is never a key on its own; the slug keeps its words but loses the numeric suffix
    assert subject_keys({"full_name": "Jo Li", "slug": "jo-li-1a2b3c"}) == ["jo li", "jo-li"]


def _c(url, title="", snippet="", queries=("q",)):
    return {"url": url, "title": title, "snippet": snippet, "queries": list(queries)}


def test_generic_pages_are_not_fetched_and_pages_about_the_subject_are():
    cands = {c["url"]: c for c in [
        _c("https://www.adgm.com/public-registers/fsra", "Public registers", "FSRA register of firms"),
        _c("https://www.dfsa.ae/news/dfsa-fines-ark-capital", "DFSA fines Ark Capital", "USD 504,000"),
        _c("https://www.prnewswire.com/", "PR Newswire", "press releases"),
        _c("https://medium.com/@jayyanar/aws-sagemaker", "AWS SageMaker geospatial", "by Ayyanar"),
        _c("https://builder.aws.com/community/heroes/AyyanarJeyakrishnan", "AWS Heroes", "Ayyanar Jeyakrishnan, AWS Hero"),
        _c("https://github.com/jayyanar", "", "", queries=("identify",)),
    ]}
    ranked, skipped = select_candidates(cands, AJ)
    fetched = {c["url"] for c in ranked}
    assert fetched == {"https://medium.com/@jayyanar/aws-sagemaker",
                       "https://builder.aws.com/community/heroes/AyyanarJeyakrishnan", "https://github.com/jayyanar"}
    assert {c["url"] for c in skipped} == {"https://www.adgm.com/public-registers/fsra",
                                           "https://www.dfsa.ae/news/dfsa-fines-ark-capital", "https://www.prnewswire.com/"}


def test_regulator_pages_about_the_company_still_rank_first():
    cands = {c["url"]: c for c in [
        _c("https://thenational.example/mark-chahwan-interview", "Mark Chahwan on robo advice", "Sarwa's CEO", ("a", "b", "c")),
        _c("https://www.dfsa.ae/news/dfsa-fines-sarwa-digital-wealth-limited", "DFSA fines Sarwa Digital Wealth Limited", "USD 191,100"),
        _c("https://www.adgm.com/public-registers/fsra/firms/financial-firms/sarwa-digital-wealth-capital-limited-190037", "Sarwa Digital Wealth (Capital) Limited", ""),
        _c("https://www.dfsa.ae/news/dfsa-fines-ark-capital", "DFSA fines Ark Capital", "USD 504,000"),
    ]}
    ranked, skipped = select_candidates(cands, MARK)
    assert [c["url"] for c in ranked][:2] == [
        "https://www.dfsa.ae/news/dfsa-fines-sarwa-digital-wealth-limited",
        "https://www.adgm.com/public-registers/fsra/firms/financial-firms/sarwa-digital-wealth-capital-limited-190037"]
    assert [c["url"] for c in skipped] == ["https://www.dfsa.ae/news/dfsa-fines-ark-capital"]


def test_no_claims_message_is_actionable():
    sources = [{"status": "ok"}, {"status": "ok"}, {"status": "could_not_check"}]
    msg = no_claims_message(AJ, sources)
    assert "Ayyanar Jeyakrishnan" in msg and "3 pages" in msg and "2 were readable" in msg
    assert "No company was identified" in msg and "founder, CEO or fund manager" in msg
    assert "No company" not in no_claims_message(MARK, sources)
