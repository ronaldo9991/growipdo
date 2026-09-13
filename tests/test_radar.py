from datetime import datetime, timezone

from app import radar


def test_parse_subjects():
    assert radar.parse_subjects("Nidhi Hooda, Growpido") == ["Nidhi Hooda", "Growpido"]
    assert radar.parse_subjects("") == []


def test_parse_date_relative_and_absolute():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    assert radar.parse_date("3 days ago", now) == "2026-09-10"
    assert radar.parse_date("2 weeks ago", now) == "2026-08-30"
    assert radar.parse_date("Sep 10, 2026", now) == "2026-09-10"
    assert radar.parse_date("2026-09-01T10:00:00Z", now) == "2026-09-01"
    assert radar.parse_date("", now) == ""


def test_mentions_subject_uses_surname_or_brand():
    assert radar.mentions_subject("Nidhi Hooda", "Ms Hooda spoke at the event")
    assert not radar.mentions_subject("Nidhi Hooda", "Nidhi Sharma spoke")
    assert radar.mentions_subject("Growpido", "", "growpido.com/about")


def _p(about, risk, sentiment="neutral", conf=0.9):
    return {"about_subject": about, "risk": risk, "sentiment": sentiment, "confidence": conf, "reason": "", "quote": "", "model": "m"}


def test_decide_rules():
    assert radar.decide(_p("yes", "ignore"), None)["risk"] == "ignore"
    both_no = radar.decide(_p("no", "ignore"), _p("no", "watch"))
    assert both_no["about_subject"] == "no" and both_no["risk"] == "ignore" and not both_no["ambiguous"]
    unsure = radar.decide(_p("yes", "respond_now"), _p("unsure", "respond_now"))
    assert unsure["ambiguous"] and unsure["risk"] == "watch"
    agree = radar.decide(_p("yes", "respond_now", "negative"), _p("yes", "respond_now", "negative"))
    assert agree["risk"] == "respond_now" and not agree["ambiguous"]
    disagree = radar.decide(_p("yes", "respond_now"), _p("yes", "watch"))
    assert disagree["ambiguous"] and disagree["risk"] == "watch"
    mild = radar.decide(_p("yes", "ignore"), _p("yes", "watch"))
    assert mild["ambiguous"] and mild["risk"] == "watch"


def test_needs_second_opinion():
    assert not radar.needs_second_opinion(_p("yes", "ignore", "positive", 0.9))
    assert radar.needs_second_opinion(_p("yes", "ignore", "negative", 0.9))
    assert radar.needs_second_opinion(_p("unsure", "ignore", "positive", 0.9))
    assert radar.needs_second_opinion(_p("yes", "ignore", "positive", 0.5))


def test_channel():
    assert radar.channel_of("https://ae.linkedin.com/posts/x", "web") == "linkedin"
    assert radar.channel_of("https://gulfbusiness.com/x", "web") == "news"
    assert radar.channel_of("https://example.com/x", "news") == "news"
    assert radar.channel_of("https://example.com/x", "web") == "web"
