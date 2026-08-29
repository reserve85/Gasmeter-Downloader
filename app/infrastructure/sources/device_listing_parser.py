"""Parse the device file-server HTML directory listing into dates (pure)."""

from __future__ import annotations

import re
from datetime import date

_LISTING_PATTERN = re.compile(r"data_(\d{4})-(\d{2})-(\d{2})\.csv")


def parse_listing(html: str) -> list[date]:
    """Extract every ``data_YYYY-MM-DD.csv`` filename from the listing HTML.

    Robust to markup variation; returns a sorted, de-duplicated list.
    """
    found: set[date] = set()
    for match in _LISTING_PATTERN.finditer(html):
        try:
            found.add(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue  # impossible-looking dates in markup are ignored
    return sorted(found)


def day_from_filename(name: str) -> date | None:
    """Best-effort day extraction from a logfile name (data_/log_ prefixes)."""
    match = re.search(r"(?:data_|log_)(\d{4}-\d{2}-\d{2})", name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None
