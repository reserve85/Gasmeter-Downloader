"""Conversion tests: kWh formula, boundary-inclusive interval lookup, unit switch."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.conversion import (
    convert_unit,
    energy_kwh,
    factor_for_day,
    parameter_for_day,
)
from app.domain.entities import GasParameterInterval, ViewUnit


def _interval(valid_from, valid_to, cal="11.342", z="0.9589"):
    return GasParameterInterval(
        valid_from=date.fromisoformat(valid_from),
        valid_to=date.fromisoformat(valid_to) if valid_to else None,
        calorific_value=Decimal(cal),
        z_value=Decimal(z),
    )


def test_energy_kwh_formula():
    # 1 m³ * 11.342 * 0.9589 = 10.8758438 -> rounds to 10.876
    result = energy_kwh(Decimal("1"), Decimal("11.342"), Decimal("0.9589"))
    assert result == Decimal("10.876")


def test_convert_unit_identity_for_m3():
    assert convert_unit(Decimal("42"), ViewUnit.M3, Decimal("11.342"), Decimal("0.9589")) == Decimal("42")


def test_convert_unit_kwh():
    result = convert_unit(Decimal("2"), ViewUnit.KWH, Decimal("11.342"), Decimal("0.9589"))
    assert result == Decimal("21.752")


def test_parameter_for_day_boundaries_inclusive():
    intervals = [
        _interval("2026-01-01", "2026-06-30"),
        _interval("2026-07-01", None),
    ]
    assert parameter_for_day(intervals, date(2026, 6, 30)) is intervals[0]
    assert parameter_for_day(intervals, date(2026, 7, 1)) is intervals[1]
    assert parameter_for_day(intervals, date(2025, 12, 31)) is None


def test_parameter_for_day_overlap_picks_most_recent():
    intervals = [
        _interval("2026-01-01", "2026-12-31", cal="10"),
        _interval("2026-06-01", "2026-08-31", cal="11"),
    ]
    assert parameter_for_day(intervals, date(2026, 5, 31)).calorific_value == Decimal("10")
    assert parameter_for_day(intervals, date(2026, 6, 1)).calorific_value == Decimal("11")


def test_factor_for_day_fallback_defaults():
    cal, z = factor_for_day([], date(2026, 1, 1))
    assert cal == Decimal("11.342")
    assert z == Decimal("0.9589")
