"""Small helpers shared by the stages."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

STOPWORDS = set(
    """a an the and or of to in on at by for with from as is are was were be been
    being it its this that these those has have had do does did not no but if
    than then so such into over under about after before during their they them
    he she his her him we our us you your who whom which what when where why how
    also more most very can could would should may might will shall said says
    per via up out new one two three first""".split()
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def host_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Numbers keep their digits and separators stripped."""
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z'\-]+|\d[\d,\.]*", text or ""):
        low = tok.lower()
        if low[0].isdigit():
            low = low.replace(",", "").rstrip(".")
        if low in STOPWORDS or len(low) < 2:
            continue
        out.append(low)
    return out


NUMBER_RE = re.compile(
    r"(?<![\w\[/])(?:USD|AED|Dhs?|US\$|\$|€|£)?\s?\d[\d,]*(?:\.\d+)?\s?(?:billion|million|thousand|bn|mn|m|k|%|percent)?(?![\w\]/])",
    re.IGNORECASE,
)


def normalize_number(raw: str) -> str:
    """Turn '$1 billion', 'USD 1,000,000,000', '1bn' into a comparable key."""
    s = raw.lower().replace(",", "").replace("usd", "").replace("aed", "").replace("dhs", "").replace("dh", "")
    s = s.replace("us$", "").replace("$", "").replace("€", "").replace("£", "").strip()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(billion|million|thousand|bn|mn|m|k|%|percent)?", s)
    if not m:
        return s
    value = float(m.group(1))
    unit = m.group(2) or ""
    mult = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
    if unit in mult:
        value *= mult[unit]
    if unit in ("%", "percent"):
        return f"{value:g}%"
    return f"{value:g}"


def find_numbers(text: str) -> list[str]:
    """All number tokens in a text, as they appear."""
    return [m.group(0).strip() for m in NUMBER_RE.finditer(text or "")]


def number_keys(text: str) -> set[str]:
    return {normalize_number(n) for n in find_numbers(text)}


def numbers_with_units(text: str) -> list[tuple[float, str]]:
    """(value, unit) pairs where unit is usd, aed, pct or none. Years and bare identifiers stay unit none."""
    out = []
    for raw in find_numbers(text or ""):
        low = raw.lower()
        unit = "usd" if ("usd" in low or "$" in low) else "aed" if ("aed" in low or low.startswith("dh")) else "pct" if ("%" in low or "percent" in low) else "none"
        key = normalize_number(raw).rstrip("%")
        try:
            out.append((float(key), unit))
        except ValueError:
            continue
    return out


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
