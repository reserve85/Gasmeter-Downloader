"""Shared pytest fixtures: fakes, temp SQLite, sample logfiles, captured logger."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.domain.entities import (  # noqa: E402
    DayReading,
    GasParameterInterval,
    LogCategory,
    LogLevel,
    ParseResult,
    Source,
)

TESTS_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = TESTS_DIR / "samples"


class FixedClock:
    def __init__(self, today: date):
        self._today = today

    def today(self) -> date:
        return self._today

    def set(self, today: date) -> None:
        self._today = today


@pytest.fixture
def clock():
    return FixedClock(date(2026, 8, 29))


class FakeMeterRepository:
    """In-memory port implementation mirroring the SQLite trust semantics."""

    def __init__(self):
        self._data: dict[date, DayReading] = {}

    def _base(self, day: date) -> DayReading:
        existing = self._data.get(day)
        if existing is None:
            return DayReading(
                day=day, import_value=None, interpolated_value=None,
                adjusted_value=Decimal("0"), source=Source.LOGFILE,
                updated_at=datetime(2026, 1, 1),
            )
        return existing

    def get_reading(self, day: date) -> DayReading | None:
        return self._data.get(day)

    def get_readings(self, start: date | None, end: date | None) -> list[DayReading]:
        rows = list(self._data.values())
        if start is not None:
            rows = [r for r in rows if r.day >= start]
        if end is not None:
            rows = [r for r in rows if r.day <= end]
        return sorted(rows, key=lambda r: r.day)

    def all_days_with_import(self) -> set[date]:
        return {r.day for r in self._data.values() if r.import_value is not None}

    def save_import(self, day: date, value: Decimal) -> None:
        existing = self._data.get(day)
        if existing is not None and existing.source == Source.MANUAL:
            reading = DayReading(
                day=day, import_value=value,
                interpolated_value=existing.interpolated_value,
                adjusted_value=existing.adjusted_value, source=Source.MANUAL,
                updated_at=datetime(2026, 1, 1),
            )
        elif existing is not None:
            adjusted = value if existing.import_value is None else existing.adjusted_value
            reading = DayReading(
                day=day, import_value=value,
                interpolated_value=existing.interpolated_value,
                adjusted_value=adjusted, source=Source.LOGFILE,
                updated_at=datetime(2026, 1, 1),
            )
        else:
            reading = DayReading(
                day=day, import_value=value, interpolated_value=None,
                adjusted_value=value, source=Source.LOGFILE,
                updated_at=datetime(2026, 1, 1),
            )
        self._data[day] = reading

    def save_interpolated(self, day: date, value: Decimal) -> None:
        existing = self._data.get(day)
        free = existing is None or (
            existing.import_value is None and existing.source not in (Source.LOGFILE, Source.MANUAL)
        )
        if free:
            reading = DayReading(
                day=day, import_value=existing.import_value if existing else None,
                interpolated_value=value, adjusted_value=value, source=Source.INTERPOLATED,
                updated_at=datetime(2026, 1, 1),
            )
        else:
            reading = DayReading(
                day=day, import_value=existing.import_value,
                interpolated_value=value, adjusted_value=existing.adjusted_value,
                source=existing.source, updated_at=datetime(2026, 1, 1),
            )
        self._data[day] = reading

    def save_manual(self, day: date, value: Decimal) -> None:
        existing = self._data.get(day)
        self._data[day] = DayReading(
            day=day, import_value=existing.import_value if existing else None,
            interpolated_value=existing.interpolated_value if existing else None,
            adjusted_value=value, source=Source.MANUAL,
            updated_at=datetime(2026, 1, 1),
        )

    def restore_to_original(self, day: date) -> None:
        base = self._data.get(day)
        if base is None:
            return
        if base.import_value is not None:
            adjusted, source = base.import_value, Source.LOGFILE
        elif base.interpolated_value is not None:
            adjusted, source = base.interpolated_value, Source.INTERPOLATED
        else:
            adjusted, source = base.adjusted_value, base.source
        self._data[day] = DayReading(
            day=day, import_value=base.import_value,
            interpolated_value=base.interpolated_value,
            adjusted_value=adjusted, source=source,
            updated_at=datetime(2026, 1, 1),
        )

    def latest_reading_day(self) -> date | None:
        return max(self._data.keys()) if self._data else None

    def first_reading_day(self) -> date | None:
        return min(self._data.keys()) if self._data else None


class FakeGasParamRepository:
    def __init__(self, intervals: list[GasParameterInterval] | None = None):
        self._intervals: list[GasParameterInterval] = list(intervals or [])

    def all_intervals(self) -> list[GasParameterInterval]:
        return list(self._intervals)

    def upsert_interval(self, interval: GasParameterInterval) -> None:
        self._intervals = [
            i for i in self._intervals
            if not (i.valid_from == interval.valid_from and i.valid_to == interval.valid_to)
        ]
        self._intervals.append(interval)

    def delete_interval(self, valid_from: date, valid_to: date | None) -> None:
        self._intervals = [
            i for i in self._intervals
            if not (i.valid_from == valid_from and i.valid_to == valid_to)
        ]

    def parameter_for(self, day: date) -> GasParameterInterval | None:
        candidates = [
            i for i in self._intervals
            if i.valid_from <= day and (i.valid_to is None or day <= i.valid_to)
        ]
        return max(candidates, key=lambda i: i.valid_from) if candidates else None


@pytest.fixture
def fake_repo():
    return FakeMeterRepository()


@pytest.fixture
def gas_repo():
    return FakeGasParamRepository()
_OPEN_INTERVAL = GasParameterInterval(
    valid_from=date(2020, 1, 1), valid_to=None,
    calorific_value=Decimal("11.342"), z_value=Decimal("0.9589"),
)


@pytest.fixture
def open_interval():
    return _OPEN_INTERVAL


class FakeSource:
    def __init__(self):
        self.available: set[date] = set()
        self.payloads: dict[date, bytes] = {}
        self.download_calls: list[date] = []
        self.listing_mode = "normal"  # normal | raise | empty

    def available_days(self) -> list[date]:
        if self.listing_mode == "raise":
            raise RuntimeError("device down")
        if self.listing_mode == "empty":
            return []
        return sorted(self.available)

    def download(self, day: date, target_dir: Path) -> Path | None:
        self.download_calls.append(day)
        if day not in self.payloads:
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"data_{day.isoformat()}.csv"
        target.write_bytes(self.payloads[day])
        return target


class FakeParser:
    def __init__(self):
        self.results: dict[str, ParseResult] = {}
        self.parse_calls: list[str] = []

    def add_csv(self, path: Path, day: date, value: Decimal | None) -> None:
        self.results[path.name] = ParseResult(
            day=day, value=value, rows_read=1, candidates=1, note="fake",
        )

    def parse(self, path: Path) -> ParseResult:
        self.parse_calls.append(path.name)
        result = self.results.get(path.name)
        if result is None:
            return ParseResult(day=date.today(), value=None, rows_read=0, candidates=0, note="unknown")
        return result


class FakeArchiver:
    def __init__(self):
        self.moved: list[Path] = []
        self._store: dict[str, Path] = {}

    def archive(self, path: Path) -> Path | None:
        self.moved.append(path)
        self._store[path.name] = path
        return path

    def is_archived(self, path: Path) -> bool:
        return path.name in self._store

    def find_by_date(self, day: date) -> Path | None:
        prefix = f"data_{day.isoformat()}"
        for name, path in self._store.items():
            if prefix in name:
                return path
        return None


class FakeSettings:
    def __init__(self, values: dict | None = None):
        self._values: dict = dict(values or {})

    def get(self, key: str, default=None):
        return self._values.get(key, default)

    def set(self, key: str, value) -> None:
        self._values[key] = value

    def to_dict(self) -> dict:
        return dict(self._values)


class RecordingLogger:
    def __init__(self):
        self.events: list[tuple[LogCategory, LogLevel, str]] = []
        self.history_lines: list[str] = []

    def log(self, category: LogCategory, level: LogLevel, message: str) -> None:
        self.events.append((category, level, message))
        self.history_lines.append(f"[{level.value}] <{category.value}> {message}")

    def messages_of(self, category: LogCategory) -> list[str]:
        return [message for cat, _, message in self.events if cat == category]

    def text(self) -> str:
        return "\n".join(m for _, _, m in self.events)


@pytest.fixture
def logger():
    return RecordingLogger()


@pytest.fixture
def source():
    return FakeSource()


@pytest.fixture
def parser():
    return FakeParser()


@pytest.fixture
def archiver():
    return FakeArchiver()


@pytest.fixture
def samples() -> dict[str, Path]:
    return {
        "csv_2022": SAMPLES_DIR / "data_2022-11-29.csv",
        "csv_2026": SAMPLES_DIR / "data_2026-08-27.csv",
        "txt_2022": SAMPLES_DIR / "log_2022-11-20.txt",
    }


@pytest.fixture
def sqlite_db(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app
