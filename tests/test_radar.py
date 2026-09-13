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


def test_second_opinion_when_title_lacks_subject():
    c = _p("yes", "ignore", "positive", 0.9)
    assert not radar.needs_second_opinion(c, {"subject": "Nidhi Hooda", "title": "Nidhi Hooda's Post"})
    assert radar.needs_second_opinion(c, {"subject": "Nidhi Hooda", "title": "Nidhi Vohra appointed CBO"})


class FakeLLM:
    model = "fake"
    def __init__(self, reply="Thank you for raising this. We will look into it and follow up."):
        self.reply = reply
        self.calls = 0
    def text(self, system, user, max_tokens=0, temperature=0.0):
        self.calls += 1
        return self.reply


def _radar_run(tmp_path, monkeypatch):
    from app import config
    from app.ledger import Run
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    run = Run.create("Nidhi Hooda", kind="radar")
    run.state["models"] = {"primary": "a", "second_opinion": "b"}
    run.ledger["profile"] = {"profile": "Founder of Growpido", "disambiguators": []}
    run.ledger["mentions"] = [{"id": "M1", "subject": "Nidhi Hooda", "title": "Complaint about Growpido", "snippet": "Not happy",
                               "url": "https://x", "channel": "web", "final": {"about_subject": "yes", "risk": "respond_now", "sentiment": "negative", "ambiguous": False, "why": "both agree"},
                               "pass1": {"reason": "complaint", "model": "a"}, "pass2": None}]
    run.ledger["responses"] = {}
    run.state["status"] = "draft"
    run.save()
    return run


def test_no_draft_exists_until_a_human_approves_drafting(tmp_path, monkeypatch):
    run = _radar_run(tmp_path, monkeypatch)
    llm = FakeLLM()
    assert run.ledger["responses"] == {} and llm.calls == 0
    import pytest
    with pytest.raises(RuntimeError):
        radar.request_response(run, "M1", "", "", llm=llm)  # no name, no draft
    assert llm.calls == 0
    radar.request_response(run, "M1", "Ronaldo", "keep it short and factual", llm=llm)
    r = run.ledger["responses"]["M1"]
    assert llm.calls == 1 and r["status"] == "draft" and r["requested_by"] == "Ronaldo"


def test_draft_needs_second_approval_and_is_never_sent(tmp_path, monkeypatch):
    run = _radar_run(tmp_path, monkeypatch)
    radar.request_response(run, "M1", "Ronaldo", "keep it short", llm=FakeLLM())
    import pytest
    with pytest.raises(RuntimeError):
        radar.approve_response(run, "M2", "Ronaldo", "")  # nothing waiting on M2
    radar.approve_response(run, "M1", "Ronaldo", "edited the tone", edited="Thanks for flagging this, we are looking into it.")
    r = run.ledger["responses"]["M1"]
    assert r["status"] == "approved" and r["edited"] and r["approved_by"] == "Ronaldo"
    assert "sent" not in r  # the system records readiness, it never posts


def test_resolve_ambiguous_records_the_human(tmp_path, monkeypatch):
    run = _radar_run(tmp_path, monkeypatch)
    run.ledger["mentions"][0]["final"] = {"about_subject": "unsure", "risk": "watch", "sentiment": "neutral", "ambiguous": True, "why": "split"}
    run.save()
    radar.resolve_ambiguous(run, "M1", "Ronaldo", "no", "watch", "different person, a physician")
    f = run.ledger["mentions"][0]["final"]
    assert f["about_subject"] == "no" and f["risk"] == "ignore" and not f["ambiguous"] and f["decided_by"] == "Ronaldo"


def test_brief_lines_strip_hashtags_and_em_dashes():
    m = {"id": "M1", "title": "#podcast Growpido — the founder story", "url": "https://x", "publisher": "linkedin.com", "channel": "linkedin",
         "date": "", "final": {"sentiment": "positive", "why": "both agree"}, "pass1": {"reason": "own post #growpido"}}
    line = radar._line(m)
    assert "#" not in line and "—" not in line and "podcast Growpido" in line
