"""Unit conversion and gas-parameter lookup (pure domain logic)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.domain.entities import GasParameterInterval, ViewUnit

# Config defaults mirrored in app/infrastructure/config/config_repository.py
DEFAULT_CALORIFIC = Decimal("11.342")
DEFAULT_Z_VALUE = Decimal("0.9589")

_QUANTUM = Decimal("0.001")


def energy_kwh(volume_m3: Decimal, calorific_value: Decimal, z_value: Decimal) -> Decimal:
    """kWh = m³ * calorific_value * z_value."""
    return (volume_m3 * calorific_value * z_value).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def convert_unit(
    volume_m3: Decimal,
    unit: ViewUnit,
    calorific_value: Decimal,
    z_value: Decimal,
) -> Decimal:
    """Identity for M3, kWh conversion for KWH."""
    if unit == ViewUnit.M3:
        return volume_m3
    return energy_kwh(volume_m3, calorific_value, z_value)


def parameter_for_day(
    intervals: list[GasParameterInterval],
    day: date,
) -> GasParameterInterval | None:
    """Return the interval governing ``day``.

    Intervals normally never overlap (validated on upsert). If they do, the most
    recent interval (largest ``valid_from``) wins deterministically.
    """
    candidates = [i for i in intervals if i.valid_from <= day and (i.valid_to is None or day <= i.valid_to)]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i.valid_from)


def factor_for_day(
    intervals: list[GasParameterInterval],
    day: date,
) -> tuple[Decimal, Decimal]:
    """Return ``(calorific, z)`` for a day; falls back to config defaults, mirroring
    the domain-level fallback for days not covered by any interval."""
    interval = parameter_for_day(intervals, day)
    if interval is None:
        return DEFAULT_CALORIFIC, DEFAULT_Z_VALUE
    return interval.calorific_value, interval.z_value


def point_value(point, unit: ViewUnit) -> Decimal:
    """Resolve a consumption point's value in the requested unit (already precomputed)."""
    if unit == ViewUnit.KWH:
        return point.energy_kwh
    return point.volume_m3


def value_in_unit(
    volume_m3: Decimal | None,
    unit: ViewUnit,
    calorific: Decimal,
    z: Decimal,
) -> Decimal | None:
    """Convert a single m³ value to the display unit (None stays None)."""
    if volume_m3 is None:
        return None
    return convert_unit(volume_m3, unit, calorific, z)
