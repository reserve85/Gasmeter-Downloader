"""Daily/weekly/monthly consumption buckets, YoY pairing, OLS trendline + projection.

All functions are pure: they accept plain lists and return plain data. Logging
is the responsibility of the application layer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from app.domain.conversion import energy_kwh, factor_for_day, point_value
from app.domain.entities import (
    Aggregation,
    ConsumptionPoint,
    DataSeries,
    GasParameterInterval,
    KpiSummary,
    MeterPoint,
    Source,
    Trendline,
    ViewUnit,
)

_QUANTUM = Decimal("0.001")
_DEFAULT_TREND_HORIZON = 30  # days

# Approximate fallback factor for trend projections so both fields stay filled;
# the fitted line is drawn in the selected unit.
_FALLBACK_FACTOR = Decimal("10.868")  # ~ default_calorific * default_z


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def consumption_series(
    readings: list,
    start: date,
    end: date,
    unit: ViewUnit,
    intervals: list[GasParameterInterval],
) -> list[ConsumptionPoint]:
    """Daily Δ adjusted_value, converted per day to the requested unit.

    ``readings`` must include the day before ``start`` (the boundary the first
    day consumes). If a day (or its predecessor) is missing, the day is omitted.
    Negative differences (meter resets / manual corrections) are kept as-is.
    """
    by_day = {r.day: r for r in readings}
    points: list[ConsumptionPoint] = []
    day = start
    while day <= end:
        cur = by_day.get(day)
        prev = by_day.get(day - timedelta(days=1))
        if cur is None or prev is None:
            day += timedelta(days=1)
            continue
        delta = _q(cur.adjusted_value - prev.adjusted_value)
        cal, z = factor_for_day(intervals, day)
        points.append(
            ConsumptionPoint(
                day=day,
                volume_m3=delta,
                energy_kwh=energy_kwh(delta, cal, z),
            )
        )
        day += timedelta(days=1)
    return points


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _month_start(day: date) -> date:
    return day.replace(day=1)


def aggregate(points: list[ConsumptionPoint], agg: Aggregation) -> list[ConsumptionPoint]:
    """Group consecutive days into ISO-week or calendar-month buckets (summed)."""
    if agg == Aggregation.DAILY:
        return sorted(points, key=lambda p: p.day)
    anchor_fn = _week_start if agg == Aggregation.WEEKLY else _month_start
    buckets: dict[date, list[ConsumptionPoint]] = {}
    for p in points:
        buckets.setdefault(anchor_fn(p.day), []).append(p)
    result: list[ConsumptionPoint] = []
    for anchor in sorted(buckets):
        group = buckets[anchor]
        volume = sum((p.volume_m3 for p in group), Decimal("0"))
        energy = sum((p.energy_kwh for p in group), Decimal("0"))
        result.append(ConsumptionPoint(day=anchor, volume_m3=_q(volume), energy_kwh=_q(energy)))
    return result


def aggregate_all(points: list[ConsumptionPoint]) -> dict[Aggregation, list[ConsumptionPoint]]:
    """Precompute DAILY, WEEKLY and MONTHLY buckets in one pass (instant UI switching)."""
    return {
        Aggregation.DAILY: aggregate(points, Aggregation.DAILY),
        Aggregation.WEEKLY: aggregate(points, Aggregation.WEEKLY),
        Aggregation.MONTHLY: aggregate(points, Aggregation.MONTHLY),
    }
def _prev_anchor(anchor: date, agg: Aggregation) -> date | None:
    if agg == Aggregation.DAILY:
        try:
            return anchor.replace(year=anchor.year - 1)
        except ValueError:  # Feb 29 -> Feb 28
            return anchor.replace(year=anchor.year - 1, day=28)
    if agg == Aggregation.MONTHLY:
        try:
            return anchor.replace(year=anchor.year - 1)
        except ValueError:
            return anchor.replace(year=anchor.year - 1, day=28)
    # WEEKLY: same ISO week number in the previous ISO year
    iso_year, iso_week, _ = anchor.isocalendar()
    try:
        return date.fromisocalendar(iso_year - 1, iso_week, 1)
    except ValueError:
        return None  # ISO week 53 does not exist in the previous year


def shift_previous(anchor: date, agg: Aggregation) -> date | None:
    """Public version of the previous-year anchor mapping (used by charts too)."""
    return _prev_anchor(anchor, agg)


def previous_year_buckets(
    current: list[ConsumptionPoint],
    prev_buckets: list[ConsumptionPoint],
    agg: Aggregation,
) -> list[ConsumptionPoint] | None:
    """Pair current buckets with the same buckets one year earlier.

    ``prev_buckets`` must already contain the previous year's buckets for the
    same aggregation (in the same unit). Returns None when there is no
    previous-year data at all.
    """
    if not prev_buckets:
        return None
    prev_by_anchor = {p.day: p for p in prev_buckets}
    paired: list[ConsumptionPoint] = []
    for bucket in current:
        target = _prev_anchor(bucket.day, agg)
        if target is None or target not in prev_by_anchor:
            continue
        paired.append(prev_by_anchor[target])
    return paired or None


def compute_kpis(
    daily: list[ConsumptionPoint],
    readings: list,
    unit: ViewUnit,
    intervals: list[GasParameterInterval],
) -> KpiSummary:
    """Total / average / max day / interpolated count / latest meter value."""
    unit_values = [point_value(p, unit) for p in daily]
    total = sum(unit_values, Decimal("0"))
    average = _q(total / Decimal(len(unit_values))) if unit_values else Decimal("0")
    max_day: ConsumptionPoint | None = None
    if daily:
        max_day = max(daily, key=lambda p: point_value(p, unit))
    days = {r.day for r in daily}
    interpolated = sum(1 for r in readings if r.day in days and r.source == Source.INTERPOLATED)
    latest_meter: Decimal | None = None
    if readings:
        latest = max(readings, key=lambda r: r.day)
        cal, z = factor_for_day(intervals, latest.day)
        if unit == ViewUnit.KWH:
            latest_meter = energy_kwh(latest.adjusted_value, cal, z)
        else:
            latest_meter = latest.adjusted_value
    return KpiSummary(
        total_energy=_q(total),
        average_per_day=average,
        max_day=max_day,
        interpolated_days_in_range=interpolated,
        latest_meter_value=latest_meter,
    )


def build_meter_series(
    readings: list,
    start: date,
    end: date,
    unit: ViewUnit,
    intervals: list[GasParameterInterval],
) -> list[MeterPoint]:
    """Cumulative meter line (adjusted values) in the selected unit, sorted."""
    in_range = sorted((r for r in readings if start <= r.day <= end), key=lambda r: r.day)
    series: list[MeterPoint] = []
    for r in in_range:
        cal, z = factor_for_day(intervals, r.day)
        display = r.adjusted_value if unit == ViewUnit.M3 else energy_kwh(r.adjusted_value, cal, z)
        series.append(
            MeterPoint(
                day=r.day,
                adjusted_value=r.adjusted_value,
                display_value=display,
                source=r.source,
                interpolated=r.source == Source.INTERPOLATED,
            )
        )
    return series


def linear_regression(points: list[ConsumptionPoint], unit: ViewUnit) -> tuple[Decimal, Decimal, Decimal]:
    """OLS slope, intercept, R² over daily consumption in the selected unit.

    Returns (0, 0, 0) for degenerate input (no / single point / zero variance).
    """
    xs = [p.day.toordinal() for p in points]
    ys = [float(point_value(p, unit)) for p in points]
    n = len(xs)
    if n < 2:
        return Decimal("0"), Decimal("0"), Decimal("0")
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    syy = sum(y * y for y in ys)
    denom = n * sxx - sx * sx
    if denom == 0:
        return Decimal("0"), Decimal("0"), Decimal("0")
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    resid = n * syy - sy * sy
    if resid == 0:
        r2 = Decimal("0")
    else:
        corr_num = n * sxy - sx * sy
        r2 = Decimal((corr_num * corr_num) / (denom * resid))
    return Decimal(f"{slope:.6f}"), Decimal(f"{intercept:.6f}"), r2


def _forecast_point(day: date, value: Decimal, unit: ViewUnit) -> ConsumptionPoint:
    if unit == ViewUnit.KWH:
        return ConsumptionPoint(day=day, volume_m3=_q(value / _FALLBACK_FACTOR), energy_kwh=_q(value))
    return ConsumptionPoint(day=day, volume_m3=_q(value), energy_kwh=_q(value * _FALLBACK_FACTOR))


def project_trend(
    slope: Decimal,
    intercept: Decimal,
    last_day: date,
    horizon_days: int = _DEFAULT_TREND_HORIZON,
    unit: ViewUnit = ViewUnit.M3,
) -> list[ConsumptionPoint]:
    """Per-day projection extended ``horizon_days`` beyond the data (exclusive).

    The OLS intercept is anchored at ordinal day 0, so the projection continues
    the fitted line from ``last_day``'s ordinal, not from zero.
    """
    base_ordinal = last_day.toordinal()
    points: list[ConsumptionPoint] = []
    for offset in range(1, horizon_days + 1):
        day = last_day + timedelta(days=offset)
        value = slope * Decimal(base_ordinal + offset) + intercept
        points.append(_forecast_point(day, value, unit))
    return points


def build_trendline(
    daily: list[ConsumptionPoint],
    unit: ViewUnit,
    horizon_days: int = _DEFAULT_TREND_HORIZON,
) -> Trendline | None:
    """OLS trendline over daily consumption plus a forward projection."""
    if len(daily) < 2:
        return None
    slope, intercept, r2 = linear_regression(daily, unit)
    fitted = [
        ConsumptionPoint(
            day=p.day,
            volume_m3=_q(slope * Decimal(p.day.toordinal()) + intercept),
            energy_kwh=_q(slope * Decimal(p.day.toordinal()) + intercept),
        )
        for p in daily
    ]
    forecast = project_trend(slope, intercept, daily[-1].day, horizon_days, unit)
    series = fitted + forecast
    return Trendline(
        slope=slope,
        intercept=intercept,
        r2=r2,
        series=DataSeries(name="trend", unit=unit, points=series),
    )
