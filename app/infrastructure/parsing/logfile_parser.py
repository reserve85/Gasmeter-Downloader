"""Dispatch logfile parsing by file suffix."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.domain.entities import ParseResult
from app.infrastructure.parsing.csv_parser import CsvLogfileParser
from app.infrastructure.parsing.text_parser import TextLogfileParser
from app.infrastructure.sources.device_listing_parser import day_from_filename


class LogfileParser:
    def __init__(self):
        self._csv = CsvLogfileParser()
        self._txt = TextLogfileParser()

    def parse(self, path: Path) -> ParseResult:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self._csv.parse(path)
        if suffix == ".txt":
            return self._txt.parse(path)
        return ParseResult(
            day=day_from_filename(path.name) or date.today(),
            value=None,
            rows_read=0,
            candidates=0,
            note=f"unsupported file type: {suffix or '(none)'}",
        )
