"""Domain entities and enums.

All value objects are frozen dataclasses. Numeric values use ``decimal.Decimal``
inside the domain; the SQLite layer stores REAL and converts back to Decimal
(round-tripping through ``str`` to avoid binary float artifacts).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path


class Source(str, Enum):
    LOGFILE = "logfile"  # value came from a logfile
    INTERPOLATED = "interpolated"  # value filled by linear interpolation
    MANUAL = "manual"  # value set/corrected by the user


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Aggregation(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ViewUnit(str, Enum):
    M3 = "m³"
    KWH = "kWh"


class Language(str, Enum):
    AUTO = "auto"
    EN = "en"
    DE = "de"


class LogCategory(str, Enum):
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    DOWNLOAD = "DOWNLOAD"
    PARSE = "PARSE"
    IMPORT = "IMPORT"
    IGNORE = "IGNORE"
    ARCHIVE = "ARCHIVE"
    INTERPOLATE = "INTERPOLATE"
    EDIT = "EDIT"
    RESTORE = "RESTORE"
    SETTINGS = "SETTINGS"
    GAS_PARAMS = "GAS_PARAMS"
    GUI = "GUI"
    UPDATE = "UPDATE"
    DB = "DB"
    THEME = "THEME"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class DayReading:
    day: date
    import_value: Decimal | None  # raw meter value from logfile (never overwritten)
    interpolated_value: Decimal | None  # last computed interpolation (restore target w/o import)
    adjusted_value: Decimal  # effective value used everywhere (modified > imported > interpolated)
    source: Source
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GasParameterInterval:
    valid_from: date  # inclusive
    valid_to: date | None  # inclusive; None = open-ended
    calorific_value: Decimal  # kWh/m³ (Hs)
    z_value: Decimal  # Z-number (compression factor)

    def contains(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


@dataclass(frozen=True, slots=True)
class ParseResult:
    day: date
    value: Decimal | None  # extracted last successful reading (None = unusable)
    rows_read: int
    candidates: int  # successful rows considered
    note: str  # summary for logging


@dataclass(frozen=True, slots=True)
class GapFill:
    """One interpolated day."""

    day: date
    value: Decimal


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    day: date
    status: str  # imported | already-present | no-value | outside-window
    value: Decimal | None
    note: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    downloaded: list[date]
    imported: list[ImportOutcome]
    missing_on_device: list[date]  # HTTP 404 / not listed -> warning
    failed: list[tuple[date, str]]  # download/parse/archive errors
    archived: list[Path]


@dataclass(frozen=True, slots=True)
class ConsumptionPoint:
    day: date
    volume_m3: Decimal  # Δ adjusted_value for the bucket
    energy_kwh: Decimal  # same bucket converted per contributing day


@dataclass(frozen=True, slots=True)
class DataSeries:
    name: str
    unit: ViewUnit
    points: list[ConsumptionPoint]


@dataclass(frozen=True, slots=True)
class Trendline:
    slope: Decimal
    intercept: Decimal
    r2: Decimal
    series: DataSeries  # fitted line over the selected range


@dataclass(frozen=True, slots=True)
class MeterPoint:
    day: date
    adjusted_value: Decimal  # meter progression from DB (m³)
    display_value: Decimal  # converted to current view unit
    source: Source


@dataclass(frozen=True, slots=True)
class KpiSummary:
    total_energy: Decimal
    average_per_day: Decimal
    max_day: ConsumptionPoint | None
    interpolated_days_in_range: int
    latest_meter_value: Decimal | None
    year_consumed: Decimal = Decimal("0")  # consumption since Jan 1 (selected unit)
    year_projection: Decimal = Decimal("0")  # full-year estimate incl. remainder (selected unit)
    projection_basis: str = ""  # "" | "current-year" | "previous-year"
    projection_year: int = 0  # year being projected


@dataclass(frozen=True, slots=True)
class Dashboard:
    unit: ViewUnit
    meter_series: list[MeterPoint]
    consumption: dict[Aggregation, list[ConsumptionPoint]]
    previous_year: dict[Aggregation, list[ConsumptionPoint]] | None
    trendline: Trendline | None
    kpi: KpiSummary
    table_rows: list[tuple[date, Decimal | None, Decimal | None, Decimal, Source]]
    day_factors: dict[date, tuple[Decimal, Decimal]]  # (calorific, z) valid per day
