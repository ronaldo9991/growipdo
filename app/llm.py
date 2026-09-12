"""Model wrapper. Two providers: Anthropic messages API, or any OpenAI compatible chat completions endpoint.

Selected by LLM_PROVIDER in .env: "anthropic" (default) or "openai".
For "openai" set OPENAI_API_KEY, optionally OPENAI_BASE_URL (default https://api.openai.com/v1).
"""
from __future__ import annotations

import json
import re

import httpx

from . import config


class ModelError(RuntimeError):
    pass


def parse_json(text: str):
    """Pull the first JSON object or array out of a model reply."""
    if text is None:
        raise ModelError("empty reply")
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if not starts:
        raise ModelError(f"no JSON in reply: {s[:200]!r}")
    start = min(starts)
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s[start:])
        return obj
    except json.JSONDecodeError as e:
        raise ModelError(f"bad JSON from model: {e}; reply began {s[:200]!r}") from e


def provider() -> str:
    return (config.get("LLM_PROVIDER") or "anthropic").strip().lower()


def openai_base_url() -> str:
    return (config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def list_models() -> list[str]:
    if provider() == "openai":
        r = httpx.get(openai_base_url() + "/models",
                      headers={"Authorization": "Bearer " + config.require("OPENAI_API_KEY")}, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        return [m.get("id") for m in items or [] if isinstance(m, dict) and m.get("id")]
    r = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": config.require("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
        timeout=30,
    )
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


class LLM:
    def __init__(self, model: str, log=None):
        self.model = model
        self.log = log
        self.provider = provider()
        if self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
        elif self.provider == "openai":
            self.api_key = config.require("OPENAI_API_KEY")
            self.base_url = openai_base_url()
        else:
            raise RuntimeError(f"unknown LLM_PROVIDER {self.provider!r}; use anthropic or openai")

    def text(self, system: str, user: str, max_tokens: int = 2000, temperature: float = 0.0) -> str:
        if self.provider == "anthropic":
            return self._anthropic(system, user, max_tokens, temperature)
        return self._openai(system, user, max_tokens, temperature)

    def _anthropic(self, system, user, max_tokens, temperature) -> str:
        msg = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature, system=system,
            messages=[{"role": "user", "content": user}],
        )
        out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if self.log:
            self.log("llm", f"{self.model}: {msg.usage.input_tokens} in, {msg.usage.output_tokens} out", stop=msg.stop_reason)
        if msg.stop_reason == "max_tokens":
            raise ModelError(f"{self.model} hit max_tokens={max_tokens}; raise the limit")
        return out

    def _openai(self, system, user, max_tokens, temperature) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            r = httpx.post(self.base_url + "/chat/completions", json=payload, timeout=180,
                           headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise ModelError(f"{self.model}: request failed: {e}") from e
        if r.status_code != 200:
            raise ModelError(f"{self.model}: HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ModelError(f"{self.model}: unexpected reply shape: {str(data)[:400]}") from e
        if isinstance(content, list):  # some servers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        usage = data.get("usage") or {}
        if self.log:
            self.log("llm", f"{self.model}: {usage.get('prompt_tokens', '?')} in, {usage.get('completion_tokens', '?')} out",
                     stop=choice.get("finish_reason"))
        if choice.get("finish_reason") == "length":
            raise ModelError(f"{self.model} hit max_tokens={max_tokens}; raise the limit")
        return content or ""

    def json(self, system: str, user: str, max_tokens: int = 3000):
        """Ask for JSON. One retry with a nudge if the first reply does not parse."""
        system_json = system + "\n\nReply with JSON only. No prose before or after it."
        reply = self.text(system_json, user, max_tokens=max_tokens)
        try:
            return parse_json(reply)
        except ModelError as first:
            if self.log:
                self.log("llm", f"{self.model}: JSON parse failed, retrying once", error=str(first))
            nudge = user + "\n\nYour previous reply was not valid JSON. Return only the JSON."
            reply = self.text(system_json, nudge, max_tokens=max_tokens)
            return parse_json(reply)
