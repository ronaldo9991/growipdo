"""Web search behind one function. Public web only; LinkedIn results are dropped, never read.

SEARCH_PROVIDER in .env picks the backend:
  tavily      TAVILY_API_KEY      https://tavily.com          1,000 free credits a month
  brave       BRAVE_API_KEY       https://brave.com/search/api  free tier, JSON web results
  serper      SERPER_API_KEY      https://serper.dev          Google results, free starter credits
  duckduckgo  no key              scrapes the HTML endpoint; brittle, rate limited, last resort
All return [{url, title, snippet, score, query}]."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from . import config
from .util import host_of


class SearchError(RuntimeError):
    pass


def is_blocked(url: str) -> bool:
    host = host_of(url)
    return any(host == b or host.endswith("." + b) for b in config.BLOCKED_HOSTS)


def provider() -> str:
    return (config.get("SEARCH_PROVIDER") or "tavily").strip().lower()


def _clean(results: list[dict], query: str) -> list[dict]:
    out, seen = [], set()
    for r in results:
        url = (r.get("url") or "").split("#")[0]
        if not url or url in seen or is_blocked(url):
            continue
        seen.add(url)
        out.append({"url": url, "title": (r.get("title") or "").strip(), "snippet": (r.get("snippet") or "").strip(),
                    "score": r.get("score"), "query": query})
    return out


def _post(url, **kw):
    try:
        return httpx.post(url, timeout=40, **kw)
    except httpx.HTTPError as e:
        raise SearchError(f"search request failed: {e}") from e


def _get(url, **kw):
    try:
        return httpx.get(url, timeout=40, follow_redirects=True, **kw)
    except httpx.HTTPError as e:
        raise SearchError(f"search request failed: {e}") from e


def tavily(query: str, max_results: int) -> list[dict]:
    r = _post("https://api.tavily.com/search", json={"api_key": config.require("TAVILY_API_KEY"), "query": query,
                                                     "max_results": max_results, "search_depth": "advanced"})
    if r.status_code != 200:
        raise SearchError(f"tavily returned {r.status_code} for {query!r}: {r.text[:300]}")
    return [{"url": i.get("url"), "title": i.get("title"), "snippet": i.get("content"), "score": i.get("score")}
            for i in r.json().get("results", [])]


def brave(query: str, max_results: int) -> list[dict]:
    r = _get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": max_results},
             headers={"X-Subscription-Token": config.require("BRAVE_API_KEY"), "Accept": "application/json"})
    if r.status_code != 200:
        raise SearchError(f"brave returned {r.status_code} for {query!r}: {r.text[:300]}")
    items = (r.json().get("web") or {}).get("results") or []
    return [{"url": i.get("url"), "title": i.get("title"), "snippet": i.get("description"), "score": None} for i in items]


def serper(query: str, max_results: int) -> list[dict]:
    r = _post("https://google.serper.dev/search", json={"q": query, "num": max_results},
              headers={"X-API-KEY": config.require("SERPER_API_KEY"), "Content-Type": "application/json"})
    if r.status_code != 200:
        raise SearchError(f"serper returned {r.status_code} for {query!r}: {r.text[:300]}")
    items = r.json().get("organic") or []
    return [{"url": i.get("link"), "title": i.get("title"), "snippet": i.get("snippet"), "score": None} for i in items]


_DDG_LINK = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_DDG_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>|<td class="result-snippet">(.*?)</td>', re.DOTALL)


def _strip(t: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()


def parse_duckduckgo(page: str) -> list[dict]:
    """Each result is a result__a link followed (before the next link) by an optional snippet."""
    out = []
    links = list(_DDG_LINK.finditer(page))
    for i, m in enumerate(links):
        href, title = m.groups()
        if "uddg=" in href:  # DDG wraps targets in a redirect
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
        if not href.startswith("http"):
            continue
        tail = page[m.end(): links[i + 1].start() if i + 1 < len(links) else len(page)]
        sm = _DDG_SNIPPET.search(tail)
        snippet = _strip((sm.group(1) or sm.group(2)) if sm else "")
        out.append({"url": href, "title": _strip(title), "snippet": snippet, "score": None})
    return out


def duckduckgo(query: str, max_results: int) -> list[dict]:
    r = _post("https://html.duckduckgo.com/html/", data={"q": query},
              headers={"User-Agent": config.USER_AGENT, "Accept": "text/html"})
    if r.status_code != 200:
        raise SearchError(f"duckduckgo returned {r.status_code} for {query!r} (rate limited or blocked)")
    items = parse_duckduckgo(r.text)
    if not items and "anomaly" in r.text.lower():
        raise SearchError("duckduckgo served a bot challenge instead of results")
    return items[:max_results]


PROVIDERS = {"tavily": tavily, "brave": brave, "serper": serper, "duckduckgo": duckduckgo}


def search(query: str, max_results: int = 8) -> list[dict]:
    name = provider()
    if name not in PROVIDERS:
        raise SearchError(f"unknown SEARCH_PROVIDER {name!r}; use one of {', '.join(PROVIDERS)}")
    return _clean(PROVIDERS[name](query, max_results), query)


# Backwards compatible name used by the pipeline.
tavily_search = search
