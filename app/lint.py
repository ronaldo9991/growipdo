"""House rules linter. Flags em dashes, hashtags, filler vocabulary and untraced numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .util import find_numbers, normalize_number

EM_DASH = "—"

# Words and phrases Growpido does not publish. Matched on word boundaries, case insensitive.
FILLER = [
    "delve",
    "delves",
    "delving",
    "leverage",
    "leverages",
    "leveraging",
    "seamless",
    "seamlessly",
    "cutting-edge",
    "cutting edge",
    "game-changer",
    "game changer",
    "game-changing",
    "robust",
    "synergy",
    "synergies",
    "unlock",
    "unlocks",
    "unlocking",
    "empower",
    "empowers",
    "empowering",
    "elevate",
    "elevates",
    "elevating",
    "landscape",
    "in today's fast-paced",
    "fast-paced",
    "navigate",
    "navigating",
    "holistic",
    "tapestry",
    "testament",
    "underscores",
    "underscore",
    "pivotal",
    "realm",
    "harness",
    "harnessing",
    "streamline",
    "streamlined",
    "revolutionize",
    "revolutionary",
    "transformative",
    "unleash",
    "journey",
    "world-class",
    "state-of-the-art",
    "next-level",
    "dive into",
    "deep dive",
    "it's worth noting",
    "it is worth noting",
    "in conclusion",
    "furthermore",
    "moreover",
    "additionally",
    "crucial",
    "vibrant",
    "bustling",
    "embark",
    "foster",
    "fostering",
    "groundbreaking",
    "innovative",
    "paradigm",
    "utilize",
    "utilise",
    "utilizing",
    "excited to",
    "thrilled to",
    "passionate about",
]

_FILLER_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(f) for f in sorted(FILLER, key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"(?:^|(?<=\s))#\w+")


@dataclass
class Issue:
    kind: str
    detail: str
    line: int

    def __str__(self) -> str:
        return f"line {self.line}: {self.kind}: {self.detail}"


def lint_text(text: str) -> list[Issue]:
    issues: list[Issue] = []
    for i, line in enumerate((text or "").splitlines(), start=1):
        if EM_DASH in line:
            issues.append(Issue("em_dash", "contains an em dash", i))
        for m in _HASHTAG_RE.finditer(line):
            issues.append(Issue("hashtag", m.group(0), i))
        for m in _FILLER_RE.finditer(line):
            issues.append(Issue("filler", m.group(0), i))
    return issues


def strip_markup_for_numbers(text: str) -> str:
    """Remove list markers, finding ids like [V3] and markdown headings before number scanning."""
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)]|[-*+])\s+", "", line)
        line = re.sub(r"\[[A-Z]{1,2}\d+\]", "", line)
        line = re.sub(r"^#+\s*", "", line)
        out.append(line)
    return "\n".join(out)


def untraced_numbers(text: str, allowed_texts: list[str]) -> list[str]:
    """Numbers in text whose normalized value does not appear in any allowed text."""
    allowed: set[str] = set()
    for a in allowed_texts:
        for n in find_numbers(a or ""):
            allowed.add(normalize_number(n))
    missing = []
    for n in find_numbers(strip_markup_for_numbers(text)):
        key = normalize_number(n)
        if key not in allowed and n not in missing:
            missing.append(n)
    return missing


def mechanical_fix(text: str) -> str:
    """Last resort repairs that do not change meaning: em dashes and hashtags."""
    text = text.replace(EM_DASH, ", ")
    text = re.sub(r",\s*,", ",", text)
    text = _HASHTAG_RE.sub(lambda m: m.group(0)[1:], text)
    return text
