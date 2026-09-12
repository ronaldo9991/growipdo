from app import config
from app.fetch import html_to_text, fetch
from app.search import is_blocked


def test_html_to_text_skips_scripts():
    text, title = html_to_text("<html><head><title>T</title><script>x=1</script></head><body><p>Hello</p><div>World</div></body></html>")
    assert title == "T"
    assert "x=1" not in text
    assert "Hello" in text and "World" in text


def test_linkedin_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVIDENCE_DIR", tmp_path)
    assert is_blocked("https://www.linkedin.com/in/x")
    assert is_blocked("https://ae.linkedin.com/in/x")
    res = fetch("https://www.linkedin.com/in/markchahwan", "testrun")
    assert res.status == "blocked"
    assert (tmp_path / "testrun").exists()
