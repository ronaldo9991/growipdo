from app.research import classify_source


def test_tiers():
    assert classify_source("https://www.adgm.com/public-registers/fsra/firms/x", []) == "primary"
    assert classify_source("https://www.dfsa.ae/news/x", []) == "primary"
    assert classify_source("https://www.forbesmiddleeast.com/lists/the-middle-easts-fintech-50-2025/sarwa/", []) == "primary"
    assert classify_source("https://www.forbesmiddleeast.com/industry/x", []) == "secondary"
    assert classify_source("https://www.sarwa.co/blog/x", ["sarwa.co"]) == "company"
    assert classify_source("https://www.globenewswire.com/news-release/x", ["sarwa.co"]) == "company"
    assert classify_source("https://international-adviser.com/x", ["sarwa.co"]) == "secondary"
