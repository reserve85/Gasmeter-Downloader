"""Streaming CSV parser for current-format daily logfiles.

Format: headerless, 15-16 comma-separated columns:
``timestamp,channel,raw,value,prev,rate,?,error,…``. A row is successful when it
contains the text ``no error``; the meter value is column index 3. Error rows
(e.g. ``Neg. Rate``) have an empty value column and are skipped. The last
successful row wins. The day comes from the file name (``data_YYYY-MM-DD``),
falling back to the first row's timestamp.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.domain.entities import ParseResult
from app.infrastructure.sources.device_listing_parser import day_from_filename


class CsvLogfileParser:
    def parse(self, path: Path) -> ParseResult:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            return ParseResult(day=date.today(), value=None, rows_read=0, candidates=0, note=str(exc))

        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        day = day_from_filename(path.name)
        first_timestamp: date | None = None
        best: Decimal | None = None
        rows_read = 0
        candidates = 0

        for line in text.splitlines():
            rows_read += 1
            line = line.strip()
            if not line:
                continue
            if "no error" not in line:
                continue
            fields = line.split(",")
            if len(fields) < 4:
                continue
            if first_timestamp is None and day is None:
                first_timestamp = self._parse_timestamp(fields[0])
            raw_value = fields[3].strip().strip('"')
            if not raw_value:
                continue
            try:
                parsed = Decimal(raw_value)
            except InvalidOperation:
                continue
            if parsed < 0:
                continue
            candidates += 1
            best = parsed

        resolved_day = day if day is not None else first_timestamp
        if best is None:
            note = "no usable reading" + ("" if resolved_day else "; no day derived from file")
            return ParseResult(day=resolved_day or date.today(), value=None, rows_read=rows_read, candidates=candidates, note=note)
        src = "filename" if day is not None else "first row timestamp"
        return ParseResult(
            day=resolved_day,
            value=best,
            rows_read=rows_read,
            candidates=candidates,
            note=f"last successful reading={best} (day from {src})",
        )

    @staticmethod
    def _parse_timestamp(text: str) -> date | None:
        """Accept ISO-like timestamps with optional timezone offset."""
        stripped = text.strip().strip('"')
        try:
            return date.fromisoformat(stripped[:10])
        except ValueError:
            return None
