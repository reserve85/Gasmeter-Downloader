"""Request/response models for the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.entities import Aggregation, ViewUnit


@dataclass(frozen=True, slots=True)
class SyncRequest:
    mode: str  # "device" | "archive"
    files: list[Path]  # archive mode only


@dataclass(frozen=True, slots=True)
class ManualEditRequest:
    day: date
    value: Decimal


@dataclass(frozen=True, slots=True)
class QueryRequest:
    start: date | None
    end: date | None
    unit: ViewUnit = ViewUnit.M3
    aggregation: Aggregation = Aggregation.DAILY
    include_previous_year: bool = False
    with_trendline: bool = False
    with_year_projection: bool = False
    project_by_previous_year: bool = False


@dataclass(frozen=True, slots=True)
class ParamsIntervalRequest:
    valid_from: date
    valid_to: date | None
    calorific_value: Decimal
    z_value: Decimal
