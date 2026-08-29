"""Interpolation tests: exact values, boundary rules, idempotence, precision."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


from app.domain.entities import DayReading, Source
from app.domain.interpolation import find_gaps, interpolate_gap, recompute_gaps


def _reading(day: date, value: Decimal, source: Source = Source.LOGFILE) -> DayReading:
    if source == Source.INTERPOLATED:
        return DayReading(
            day=day, import_value=None, interpolated_value=value,
            adjusted_value=value, source=source, updated_at=None,
        )
    return DayReading(
        day=day, import_value=value, interpolated_value=None,
        adjusted_value=value, source=source, updated_at=None,
    )


def _d(iso: str) -> date:
    return date.fromisoformat(iso)


def test_find_gaps_simple():
    readings = [ _reading(_d("2026-08-10"), Decimal("100")), _reading(_d("2026-08-14"), Decimal("140")) ]
    gaps = find_gaps(readings)
    assert gaps == [(_d("2026-08-10"), _d("2026-08-14"))]


def test_find_gaps_ignores_leading_and_trailing_runs():
    readings = [
        _reading(_d("2026-08-02"), Decimal("10")),
        _reading(_d("2026-08-05"), Decimal("20")),
        _reading(_d("2026-08-15"), Decimal("30")),
    ]
    gaps = find_gaps(readings)
    # 08-03..08-04 and 08-06..08-14 are the two boundary-bounded gaps
    assert gaps == [(_d("2026-08-02"), _d("2026-08-05")), (_d("2026-08-05"), _d("2026-08-15"))]


def test_interpolate_gap_exact():
    left = _reading(_d("2026-08-10"), Decimal("100"))
    right = _reading(_d("2026-08-14"), Decimal("140"))
    fills = interpolate_gap(left, right)
    assert [(f.day, f.value) for f in fills] == [
        (_d("2026-08-11"), Decimal("110")),
        (_d("2026-08-12"), Decimal("120")),
        (_d("2026-08-13"), Decimal("130")),
    ]


def test_single_day_gap():
    left = _reading(_d("2026-08-10"), Decimal("100"))
    right = _reading(_d("2026-08-12"), Decimal("102"))
    fills = interpolate_gap(left, right)
    assert len(fills) == 1
    assert fills[0].day == _d("2026-08-11")
    assert fills[0].value == Decimal("101")


def test_long_gap_50_days():
    left = _reading(_d("2026-01-01"), Decimal("1000"))
    right = _reading(_d("2026-02-21"), Decimal("1005.1"))
    fills = interpolate_gap(left, right)
    assert len(fills) == 50
    assert fills[0].value == Decimal("1000.100")  # 5.1 / 51 = 0.1 per day


def test_decimal_precision_no_float_drift():
    left = _reading(_d("2026-01-01"), Decimal("31163.63"))
    right = _reading(_d("2026-01-04"), Decimal("31166.93"))
    fills = interpolate_gap(left, right)
    # span 3.30 over 3 steps = 1.10/day exactly in Decimal
    assert len(fills) == 2
    assert fills[1].value - fills[0].value == Decimal("1.100")
    assert fills[0].value - left.adjusted_value == Decimal("1.100")


def test_recompute_gaps_touches_only_free_and_interpolated():
    readings = [
        _reading(_d("2026-08-10"), Decimal("100")),
        _reading(_d("2026-08-11"), Decimal("110"), source=Source.INTERPOLATED),
        _reading(_d("2026-08-13"), Decimal("130"), source=Source.MANUAL),
        _reading(_d("2026-08-14"), Decimal("140")),
    ]
    fills = recompute_gaps(readings)
    by_day = {f.day: f.value for f in fills}
    # 08-12 is a free day between 08-11 (interpolated, but a boundary? no - it is
    # a present row so it becomes the left boundary) and 08-13 (manual).
    assert set(by_day) == {_d("2026-08-12")}
    # the manual day is never touched by the returned fills
    assert _d("2026-08-13") not in by_day
    # 08-11 remains a boundary; a new interpolation between 08-11 and 08-13
    assert by_day[_d("2026-08-12")] == Decimal("120")


def test_recompute_gaps_never_overwrites_manual_or_logfile():
    readings = [
        _reading(_d("2026-08-10"), Decimal("100")),
        _reading(_d("2026-08-11"), Decimal("111"), source=Source.MANUAL),
        _reading(_d("2026-08-12"), Decimal("555"), source=Source.MANUAL),
        _reading(_d("2026-08-13"), Decimal("140")),
    ]
    fills = recompute_gaps(readings)
    assert fills == []  # no free/interpolated rows exist in the bounded interior


def test_recompute_gaps_no_left_or_right_boundary():
    readings = [_reading(_d("2026-08-15"), Decimal("100"))]
    assert recompute_gaps(readings) == []
    readings.append(_reading(_d("2026-08-20"), Decimal("110")))
    fills = recompute_gaps(readings)
    # interior run 08-16..08-19 gets filled; 08-01..08-14 leading run does not
    assert len(fills) == 4
    assert all(f.day >= _d("2026-08-16") and f.day <= _d("2026-08-19") for f in fills)
