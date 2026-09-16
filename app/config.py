"""Settings. Everything comes from .env or the process environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

RUNS_DIR = Path(os.environ.get("RUNS_DIR") or ROOT / "runs")
EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR") or ROOT / "evidence")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 prospect-diagnostic/0.1"
)

# Hosts we never fetch and never read snippets from.
BLOCKED_HOSTS = ("linkedin.com",)

# Hosts whose statements count as primary sources.
PRIMARY_HOSTS = (
    "adgm.com",
    "dfsa.ae",
    "sca.gov.ae",
    "centralbank.ae",
    "difc.ae",
    "dfm.ae",
    "adx.ae",
    "moec.gov.ae",
    "u.ae",
    "gov.uk",
    "sec.gov",
    "fca.org.uk",
    "forbesmiddleeast.com/lists",
    "forbes.com/lists",
    "companieshouse.gov.uk",
)

# Wire services that carry company issued releases. Treated as the company's own word.
WIRE_HOSTS = ("globenewswire.com", "prnewswire.com", "businesswire.com", "newswire.ca", "zawya.com/en/press-release")

FETCH_TIMEOUT = 15.0   # a slow host is recorded as could not check rather than holding up the run
MAX_SOURCES = 36
MAX_COMPANY_SOURCES = 12
MAX_CLAIMS_PER_SOURCE = 10
MAX_CLAIMS_TOTAL = 72
VERIFY_WORKERS = int(os.environ.get("VERIFY_WORKERS") or 8)     # claims verified concurrently
CLAIM_WORKERS = int(os.environ.get("CLAIM_WORKERS") or 8)       # sources read for claims concurrently
CLASSIFY_WORKERS = int(os.environ.get("CLASSIFY_WORKERS") or 8) # mentions classified concurrently
FETCH_WORKERS = int(os.environ.get("FETCH_WORKERS") or 12)      # pages fetched concurrently
APPROVER_TOKEN = os.environ.get("APPROVER_TOKEN") or ""        # required on every human gate action when set
RADAR_SCHEDULE = os.environ.get("RADAR_SCHEDULE") or ""        # e.g. "mon 09:00" (UTC); empty disables the scheduler
RADAR_SUBJECTS = os.environ.get("RADAR_SUBJECTS") or "Nidhi Hooda, Growpido"
MAX_CLAIMS_PER_SOURCE_SELECTED = 3


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value
