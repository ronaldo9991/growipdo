"""Tavily web search. Public web only; LinkedIn results are dropped, never read."""
from __future__ import annotations

import httpx

from . import config
from .util import host_of


class SearchError(RuntimeError):
    pass


def is_blocked(url: str) -> bool:
    host = host_of(url)
    return any(host == b or host.endswith("." + b) for b in config.BLOCKED_HOSTS)


def tavily_search(query: str, max_results: int = 8, include_domains: list[str] | None = None,
                  api_key: str | None = None) -> list[dict]:
    key = api_key or config.require("TAVILY_API_KEY")
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        r = httpx.post("https://api.tavily.com/search", json=payload, timeout=40)
    except httpx.HTTPError as e:
        raise SearchError(f"tavily request failed for {query!r}: {e}") from e
    if r.status_code != 200:
        raise SearchError(f"tavily returned {r.status_code} for {query!r}: {r.text[:300]}")
    results = []
    for item in r.json().get("results", []):
        url = item.get("url") or ""
        if not url or is_blocked(url):
            continue
        results.append(
            {
                "url": url,
                "title": (item.get("title") or "").strip(),
                "snippet": (item.get("content") or "").strip(),
                "score": item.get("score"),
                "query": query,
            }
        )
    return results
