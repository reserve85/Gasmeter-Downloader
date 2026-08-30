"""Aggregation tests: daily deltas, weekly/monthly buckets, YoY, KPIs, OLS."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.aggregation import (
    aggregate,
    aggregate_all,
    build_meter_series,
    build_trendline,
    compute_kpis,
    consumption_series,
    linear_regression,
    previous_year_buckets,
    project_trend,
    year_projection,
)
from app.domain.conversion import energy_kwh
from app.domain.entities import (
    Aggregation,
    ConsumptionPoint,
    DayReading,
    GasParameterInterval,
    Source,
    ViewUnit,
)


def _r(iso: str, value: str, source: Source = Source.LOGFILE) -> DayReading:
    return DayReading(
        day=date.fromisoformat(iso),
        import_value=Decimal(value),
        interpolated_value=None,
        adjusted_value=Decimal(value),
        source=source,
        updated_at=None,
    )


def _p(iso: str, volume: str, energy: str | None = None) -> ConsumptionPoint:
    v = Decimal(volume)
    e = Decimal(energy) if energy else energy_kwh(v, Decimal("11.342"), Decimal("0.9589"))
    return ConsumptionPoint(day=date.fromisoformat(iso), volume_m3=v, energy_kwh=e)


_OPEN = GasParameterInterval(
    valid_from=date(2000, 1, 1), valid_to=None,
    calorific_value=Decimal("11.342"), z_value=Decimal("0.9589"),
)


def test_consumption_series_daily_deltas():
    readings = [
        _r("2026-01-01", "100"),
        _r("2026-01-02", "102"),
        _r("2026-01-03", "103.5"),
        _r("2026-01-04", "103.5"),
    ]
    points = consumption_series(readings, date(2026, 1, 1), date(2026, 1, 4), ViewUnit.M3, [_OPEN])
    assert [p.volume_m3 for p in points] == [Decimal("2"), Decimal("1.5"), Decimal("0")]
    assert points[0].day == date(2026, 1, 2)


def test_consumption_series_first_day_uses_predecessor():
    readings = [_r("2026-01-01", "100"), _r("2026-01-02", "101")]
    points = consumption_series(readings, date(2026, 1, 1), date(2026, 1, 2), ViewUnit.M3, [_OPEN])
    assert len(points) == 1
    assert points[0].day == date(2026, 1, 2)
    assert points[0].volume_m3 == Decimal("1")


def test_consumption_series_negative_delta_kept():
    readings = [_r("2026-01-05", "100"), _r("2026-01-06", "99")]
    points = consumption_series(readings, date(2026, 1, 5), date(2026, 1, 6), ViewUnit.M3, [_OPEN])
    assert points[0].volume_m3 == Decimal("-1")


def test_aggregate_weekly_iso():
    # 2026-08-24 is a Monday -> ISO week anchor
    points = [_p("2026-08-24", "1"), _p("2026-08-25", "2"), _p("2026-08-30", "3")]
    weekly = aggregate(points, Aggregation.WEEKLY)
    assert len(weekly) == 1
    assert weekly[0].day == date(2026, 8, 24)
    assert weekly[0].volume_m3 == Decimal("6")


def test_aggregate_monthly():
    points = [_p("2026-01-15", "1"), _p("2026-01-31", "2"), _p("2026-02-01", "3")]
    monthly = aggregate(points, Aggregation.MONTHLY)
    assert len(monthly) == 2
    assert monthly[0].day == date(2026, 1, 1)
    assert monthly[0].volume_m3 == Decimal("3")
    assert monthly[1].day == date(2026, 2, 1)


def test_aggregate_all_returns_three_buckets():
    points = [_p("2026-01-01", "1"), _p("2026-01-02", "2")]
    all_buckets = aggregate_all(points)
    assert set(all_buckets) == {Aggregation.DAILY, Aggregation.WEEKLY, Aggregation.MONTHLY}
    assert len(all_buckets[Aggregation.DAILY]) == 2
def test_previous_year_buckets_pairs_and_none():
    current = [_p("2026-01-05", "5"), _p("2026-02-03", "6")]
    prev = [_p("2025-01-05", "1"), _p("2025-02-03", "2")]
    paired = previous_year_buckets(current, prev, Aggregation.DAILY)
    assert paired is not None
    assert [p.volume_m3 for p in paired] == [Decimal("1"), Decimal("2")]
    assert previous_year_buckets(current, [], Aggregation.DAILY) is None


def test_previous_year_leap_day_safe():
    current = [_p("2024-02-29", "5")]
    prev = [_p("2023-02-28", "7")]
    paired = previous_year_buckets(current, prev, Aggregation.DAILY)
    assert paired is not None and paired[0].volume_m3 == Decimal("7")


def test_compute_kpis():
    readings = [
        _r("2026-01-01", "100"),
        _r("2026-01-02", "102"),
        _r("2026-01-03", "102.5"),
    ]
    daily = consumption_series(readings, date(2026, 1, 1), date(2026, 1, 3), ViewUnit.M3, [_OPEN])
    kpi = compute_kpis(daily, readings, ViewUnit.M3, [_OPEN])
    assert kpi.total_energy == Decimal("2.5")
    assert kpi.max_day.day == date(2026, 1, 2)


def test_build_meter_series():
    readings = [_r("2026-01-01", "100"), _r("2026-01-02", "102")]
    series = build_meter_series(readings, date(2026, 1, 1), date(2026, 1, 2), ViewUnit.M3, [_OPEN])
    assert [p.adjusted_value for p in series] == [Decimal("100"), Decimal("102")]
    kwh = build_meter_series(readings, date(2026, 1, 1), date(2026, 1, 2), ViewUnit.KWH, [_OPEN])
    assert kwh[1].display_value == energy_kwh(Decimal("102"), Decimal("11.342"), Decimal("0.9589"))


def test_linear_regression_perfect_line():
    points = [_p(f"2026-01-0{i}", str(2 * i)) for i in range(1, 6)]
    slope, intercept, r2 = linear_regression(points, ViewUnit.M3)
    assert slope > Decimal("1.9")
    assert abs(r2 - 1) < Decimal("0.001")


def test_linear_regression_degenerate():
    assert linear_regression([], ViewUnit.M3) == (Decimal("0"), Decimal("0"), Decimal("0"))
    assert linear_regression([_p("2026-01-01", "1")], ViewUnit.M3) == (Decimal("0"), Decimal("0"), Decimal("0"))


def test_project_trend():
    points = project_trend(Decimal("0.5"), Decimal("10"), date(2026, 1, 3), horizon_days=3, unit=ViewUnit.M3)
    assert len(points) == 3
    assert points[0].day == date(2026, 1, 4)
    assert points[-1].day == date(2026, 1, 6)


def test_build_trendline_none_for_single_point():
    assert build_trendline([_p("2026-01-01", "1")], ViewUnit.M3) is None


def test_build_trendline_has_forecast():
    points = [_p(f"2026-01-{i:02d}", str(i)) for i in range(1, 8)]
    trend = build_trendline(points, ViewUnit.M3, horizon_days=5)
    assert trend is not None
    assert len(trend.series.points) == 7 + 5


def _daily_range(start: date, end: date, volume_m3: str) -> list[ConsumptionPoint]:
    points: list[ConsumptionPoint] = []
    from datetime import timedelta

    day = start
    while day <= end:
        points.append(_p(day.isoformat(), volume_m3))
        day += timedelta(days=1)
    return points


def test_year_projection_full_year_no_remainder():
    points = _daily_range(date(2026, 1, 1), date(2026, 12, 31), "2")
    consumed, projection, basis = year_projection(
        points, date(2026, 12, 31), ViewUnit.M3, 2026
    )
    assert consumed == Decimal("730")
    assert projection == Decimal("730")
    assert basis == "current-year"


def test_year_projection_uses_elapsed_window():
    points = _daily_range(date(2026, 1, 1), date(2026, 6, 30), "1")
    consumed, projection, basis = year_projection(
        points, date(2026, 6, 30), ViewUnit.M3, 2026
    )
    assert consumed == Decimal("181")
    assert projection == Decimal("365")  # 181 + 184 remaining days * avg 1


def test_year_projection_previous_year_basis():
    current = _daily_range(date(2026, 1, 1), date(2026, 6, 30), "1")
    previous = _daily_range(date(2025, 1, 1), date(2025, 6, 30), "2")
    consumed, projection, basis = year_projection(
        current, date(2026, 6, 30), ViewUnit.M3, 2026,
        use_previous_year=True, previous_daily=previous,
    )
    assert basis == "previous-year"
    assert projection == Decimal("549")  # 181 + 184 * 2


def test_year_projection_falls_back_to_current_basis():
    current = _daily_range(date(2026, 1, 1), date(2026, 6, 30), "1")
    consumed, projection, basis = year_projection(
        current, date(2026, 6, 30), ViewUnit.M3, 2026,
        use_previous_year=True, previous_daily=[],
    )
    assert basis == "current-year"
    assert projection == Decimal("365")


def test_year_projection_empty_and_future():
    assert year_projection([], date(2026, 6, 30), ViewUnit.M3, 2026) == (
        Decimal("0"),
        Decimal("0"),
        "",
    )
    points = _daily_range(date(2026, 1, 1), date(2026, 6, 30), "1")
    assert year_projection(points, date(2026, 1, 1), ViewUnit.M3, 2027) == (
        Decimal("0"),
        Decimal("0"),
        "",
    )


def test_year_projection_kwh_unit():
    points = _daily_range(date(2026, 1, 1), date(2026, 1, 1), "1")
    consumed, projection, basis = year_projection(points, date(2026, 1, 1), ViewUnit.KWH, 2026)
    assert consumed == energy_kwh(Decimal("1"), Decimal("11.342"), Decimal("0.9589"))
    assert basis == "current-year"
