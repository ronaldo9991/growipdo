"""Fetch public pages with httpx, turn HTML into text, snapshot to evidence/."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from html.parser import HTMLParser
from pathlib import Path

import httpx

from . import config
from .search import is_blocked
from .util import now_iso, sha8, normalize_ws

SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
              "header", "footer", "td", "th", "dd", "dt", "blockquote", "pre", "table"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _Text()
    try:
        p.feed(html)
    except Exception:
        pass
    text = "".join(p.parts)
    lines = [normalize_ws(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines), normalize_ws(p.title)


@dataclass
class FetchResult:
    url: str
    status: str  # ok | could_not_check | blocked
    http_status: int | None = None
    final_url: str = ""
    title: str = ""
    text: str = ""
    error: str = ""
    snapshot: str = ""
    fetched_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chars"] = len(self.text)
        return d


def _snapshot(run_id: str, result: FetchResult) -> str:
    folder = config.EVIDENCE_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha8(result.url)}.txt"
    header = (
        f"url: {result.url}\nfinal_url: {result.final_url}\nfetched_at: {result.fetched_at}\n"
        f"status: {result.status}\nhttp_status: {result.http_status}\ntitle: {result.title}\n"
        f"error: {result.error}\n---\n"
    )
    path.write_text(header + result.text, encoding="utf-8")
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def fetch(url: str, run_id: str, client: httpx.Client | None = None) -> FetchResult:
    if is_blocked(url):
        res = FetchResult(url=url, status="blocked", error="host is on the never-fetch list")
        res.snapshot = _snapshot(run_id, res)
        return res
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=config.FETCH_TIMEOUT,
                                    headers={"User-Agent": config.USER_AGENT,
                                             "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                             "Accept-Language": "en-US,en;q=0.9"})
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        res = FetchResult(url=url, status="could_not_check", error=f"request failed: {e}")
        res.snapshot = _snapshot(run_id, res)
        if own:
            client.close()
        return res
    if own:
        client.close()
    final_url = str(r.url)
    if is_blocked(final_url):
        res = FetchResult(url=url, status="blocked", final_url=final_url, http_status=r.status_code,
                          error="redirected to a never-fetch host")
        res.snapshot = _snapshot(run_id, res)
        return res
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200:
        res = FetchResult(url=url, status="could_not_check", http_status=r.status_code, final_url=final_url,
                          error=f"HTTP {r.status_code}")
        res.snapshot = _snapshot(run_id, res)
        return res
    if "pdf" in ctype or final_url.lower().endswith(".pdf"):
        res = FetchResult(url=url, status="could_not_check", http_status=200, final_url=final_url,
                          error="PDF documents are not parsed")
        res.snapshot = _snapshot(run_id, res)
        return res
    text, title = html_to_text(r.text)
    if len(text) < 200:
        res = FetchResult(url=url, status="could_not_check", http_status=200, final_url=final_url, title=title,
                          text=text, error="page returned almost no readable text (probably rendered by JavaScript)")
        res.snapshot = _snapshot(run_id, res)
        return res
    res = FetchResult(url=url, status="ok", http_status=200, final_url=final_url, title=title, text=text)
    res.snapshot = _snapshot(run_id, res)
    return res


def read_snapshot(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = config.ROOT / p
    raw = p.read_text(encoding="utf-8")
    marker = "\n---\n"
    i = raw.find(marker)
    return raw[i + len(marker):] if i >= 0 else raw
