from app.search import parse_duckduckgo, _clean


def test_parse_ddg_redirect_links():
    page = '''<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.dfsa.ae%2Fnews%2Fx&amp;rut=abc">DFSA <b>fines</b> Sarwa</a>
    <a class="result__snippet" href="x">The DFSA has fined <b>Sarwa</b> USD 191,100</a>'''
    out = parse_duckduckgo(page)
    assert out[0]["url"] == "https://www.dfsa.ae/news/x"
    assert out[0]["title"] == "DFSA fines Sarwa"
    assert "191,100" in out[0]["snippet"]


def test_clean_drops_linkedin_and_dupes():
    raw = [{"url": "https://www.linkedin.com/in/x", "title": "", "snippet": ""},
           {"url": "https://a.com/p#frag", "title": "A", "snippet": "s"},
           {"url": "https://a.com/p", "title": "A", "snippet": "s"}]
    out = _clean(raw, "q")
    assert [r["url"] for r in out] == ["https://a.com/p"]
