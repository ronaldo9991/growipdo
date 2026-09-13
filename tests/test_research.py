from app.research import classify_source


def test_tiers():
    assert classify_source("https://www.adgm.com/public-registers/fsra/firms/x", []) == "primary"
    assert classify_source("https://www.dfsa.ae/news/dfsa-fines-x", []) == "primary"
    assert classify_source("https://www.forbesmiddleeast.com/lists/the-middle-easts-fintech-50-2025/sarwa/", []) == "primary"
    assert classify_source("https://www.forbesmiddleeast.com/industry/x", []) == "secondary"
    assert classify_source("https://www.sarwa.co/blog/x", ["sarwa.co"]) == "company"
    assert classify_source("https://www.globenewswire.com/news-release/x", ["sarwa.co"]) == "company"
    assert classify_source("https://international-adviser.com/x", ["sarwa.co"]) == "secondary"


def test_regulator_news_is_not_primary_unless_enforcement():
    assert classify_source("https://www.adgm.com/media/announcements/uaes-sarwa-hits-$1-billion-in-assets", []) == "secondary"
    assert classify_source("https://www.adgm.com/media/announcements/adgms-financial-regulator-fines-sarwa", []) == "primary"
    assert classify_source("https://www.dfsa.ae/news/dfsa-fines-sarwa-digital-wealth-limited", []) == "primary"
    assert classify_source("https://www.adgm.com/public-registers/fsra/firms/financial-firms/sarwa-190037", []) == "primary"
