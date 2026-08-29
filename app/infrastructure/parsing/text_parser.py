"""Streaming TXT parser for legacy-format daily logfiles.

Files can be ~1.2 MB; parsing is strictly line-by-line. The meter value is the
text between ``Value: `` and `` Error:`` on lines matching
``Value: <number> Error: no error``; the last match wins. The day comes from the
file name (``log_YYYY-MM-DD``), falling back to a leading ``YYYY-MM-DD``
timestamp line.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.domain.entities import ParseResult
from app.infrastructure.sources.device_listing_parser import day_from_filename

_VALUE_PATTERN = re.compile(r"Value:\s+([0-9.]+)\s+Error: no error")


class TextLogfileParser:
    def parse(self, path: Path) -> ParseResult:
        try:
            fh = open(path, "r", encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            return ParseResult(day=date.today(), value=None, rows_read=0, candidates=0, note=str(exc))

        day = day_from_filename(path.name)
        fallback_day: date | None = None
        best: Decimal | None = None
        rows_read = 0
        candidates = 0

        try:
            with fh:
                for line in fh:
                    rows_read += 1
                    if fallback_day is None and day is None and len(line) >= 10:
                        fallback_day = self._line_date(line)
                    match = _VALUE_PATTERN.search(line)
                    if not match:
                        continue
                    try:
                        parsed = Decimal(match.group(1))
                    except InvalidOperation:
                        continue
                    if parsed < 0:
                        continue
                    candidates += 1
                    best = parsed
        except UnicodeDecodeError:
            best = None

        resolved_day = day if day is not None else fallback_day
        if best is None:
            note = "no usable reading" + ("" if resolved_day else "; no day derived from file")
            return ParseResult(day=resolved_day or date.today(), value=None, rows_read=rows_read, candidates=candidates, note=note)
        return ParseResult(
            day=resolved_day,
            value=best,
            rows_read=rows_read,
            candidates=candidates,
            note=f"last successful reading={best}",
        )

    @staticmethod
    def _line_date(line: str) -> date | None:
        candidate = line[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None
