"""Linear gap-filling over daily meter readings (pure, no side effects)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN

from app.domain.entities import DayReading, GapFill, Source

_INTERP_QUANTUM = Decimal("0.001")


def find_gaps(readings: list[DayReading]) -> list[tuple[date, date]]:
    """Return boundary pairs ``(left, right)`` of present readings.

    A gap is a run of consecutive days without a reading bounded on both sides
    by a present day. Leading days before the first reading and trailing days
    after the last reading have only one boundary and are **not** gaps.
    """
    present = sorted({r.day for r in readings})
    if not present:
        return []
    present_set = set(present)
    first, last = present[0], present[-1]
    gaps: list[tuple[date, date]] = []
    run_start: date | None = None
    day = first
    while day <= last:
        if day not in present_set:
            if run_start is None:
                run_start = day
        else:
            if run_start is not None:
                gaps.append((run_start - timedelta(days=1), day))
                run_start = None
        day += timedelta(days=1)
    # A trailing run has no right boundary -> ignore.
    return gaps


def _missing_days_between(left: date, right: date) -> list[date]:
    days: list[date] = []
    day = left + timedelta(days=1)
    while day < right:
        days.append(day)
        day += timedelta(days=1)
    return days


def interpolate_gap(
    left: DayReading,
    right: DayReading,
    missing_days: list[date] | None = None,
) -> list[GapFill]:
    """Linear interpolation between two boundary readings, inclusive of day counts.

    ``missing_days`` narrows the fill (used by :func:`recompute_gaps`); when None
    every day strictly between the boundaries is interpolated.
    """
    missing = missing_days if missing_days is not None else _missing_days_between(left.day, right.day)
    total = (right.day - left.day).days
    if total <= 0:
        return []
    span = right.adjusted_value - left.adjusted_value
    fills: list[GapFill] = []
    for day in missing:
        if not (left.day < day < right.day):
            continue
        step = Decimal((day - left.day).days)
        value = left.adjusted_value + span * step / Decimal(total)
        value = value.quantize(_INTERP_QUANTUM, rounding=ROUND_HALF_EVEN)
        fills.append(GapFill(day=day, value=value))
    return fills


def recompute_gaps(readings: list[DayReading]) -> list[GapFill]:
    """Full pass over the dataset; idempotent.

    Only days with **no row** or ``source=INTERPOLATED`` are touched. Trusted
    boundary rows (logfile / manual) delimit sections; every day strictly
    between two trusted rows is re-interpolated linearly, so both missing days
    AND stale interpolated rows (e.g. after a boundary changed) are refreshed.
    Sections without a left or right boundary are not touched. Rows whose
    interpolated value is unchanged are skipped (idempotence).
    """
    by_day = {r.day: r for r in readings}
    trusted = sorted(
        (r for r in readings if r.source != Source.INTERPOLATED),
        key=lambda r: r.day,
    )
    fills: list[GapFill] = []
    for left, right in zip(trusted, trusted[1:]):
        day = left.day + timedelta(days=1)
        while day < right.day:
            candidate = interpolate_gap(left, right, [day])
            existing = by_day.get(day)
            if candidate and (
                existing is None
                or existing.interpolated_value != candidate[0].value
            ):
                fills.extend(candidate)
            day += timedelta(days=1)
    return fills
