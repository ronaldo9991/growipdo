"""Thin wrapper around the Anthropic messages API that returns parsed JSON."""
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


def list_models(api_key: str) -> list[str]:
    r = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=30,
    )
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


class LLM:
    def __init__(self, model: str, api_key: str | None = None, log=None):
        import anthropic

        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key or config.require("ANTHROPIC_API_KEY"))
        self.log = log

    def text(self, system: str, user: str, max_tokens: int = 2000, temperature: float = 0.0) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        out = "".join(parts)
        if self.log:
            self.log("llm", f"{self.model}: {msg.usage.input_tokens} in, {msg.usage.output_tokens} out", stop=msg.stop_reason)
        if msg.stop_reason == "max_tokens":
            raise ModelError(f"{self.model} hit max_tokens={max_tokens}; raise the limit")
        return out

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
