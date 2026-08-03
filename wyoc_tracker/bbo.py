"""Compatibility helpers for BBO Vugraph pages.

BBO's schedule URL without an ``offset`` query renders a JavaScript timezone
wrapper. The offset form returns the actual schedule table needed by the
non-browser GitHub Actions runner.
"""

from __future__ import annotations

import re
from types import ModuleType

SCHEDULE_URL = "https://www.bridgebase.com/vugraph/v2schedule.php?offset=0"


def matches_round(text: str, round_number: int | None) -> bool:
    """Match the common BBO round labels without guessing unrelated numbers."""

    if round_number is None:
        return True
    upper = text.upper().replace("_", " ")
    patterns = (
        rf"\bROUND\s*0*{round_number}\b",
        rf"\bRR\s*0*{round_number}\b",
        rf"\bR\s*0*{round_number}\b",
        rf"\bSW\s*0*{round_number}\b",
        rf"-SW\s*0*{round_number}\b",
        rf"\b0*{round_number}\s*/",
    )
    return any(re.search(pattern, upper) for pattern in patterns)


def configure_scraper(scraper: ModuleType) -> None:
    """Apply BBO endpoint and round-label compatibility to the scraper module."""

    scraper.VUGRAPH_URL = SCHEDULE_URL
    scraper._matches_round = matches_round
