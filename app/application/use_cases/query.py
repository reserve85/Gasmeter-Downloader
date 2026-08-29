"""Dashboard query use case - the single source for table + all chart cards."""

from __future__ import annotations

from datetime import date, timedelta

from app.application.models import QueryRequest
from app.domain.aggregation import (
    aggregate_all,
    build_meter_series,
    build_trendline,
    compute_kpis,
    consumption_series,
    previous_year_buckets,
)
from app.domain.entities import (
    Aggregation,
    Dashboard,
    LogCategory,
    LogLevel,
)
from app.domain.conversion import factor_for_day


class _DefaultClock:
    """Local fallback clock; the real one is injected from the composition root."""

    def today(self) -> date:
        return date.today()


class GetDashboardUseCase:
    """Reads readings + parameters, then produces every chart/table artifact.

    All aggregations are precomputed in one pass so that switching unit or
    aggregation in the UI is instant (no re-query of the database).
    """

    def __init__(self, repo, params_repo, settings, logger, clock=None):
        self._repo = repo
        self._params_repo = params_repo
        self._settings = settings
        self._logger = logger
        self._clock = clock or _DefaultClock()

    def run(self, request: QueryRequest) -> Dashboard:
        start, end = self._resolve_range(request)
        intervals = self._params_repo.all_intervals()
        fetch_start = start - timedelta(days=1)
        readings = self._repo.get_readings(fetch_start, end)
        unit = request.unit

        daily_points = consumption_series(readings, start, end, unit, intervals)
        consumption = aggregate_all(daily_points)

        meter_series = build_meter_series(readings, start, end, unit, intervals)

        range_readings = [r for r in readings if start <= r.day <= end]
        table_rows = [
            (r.day, r.import_value, r.interpolated_value, r.adjusted_value, r.source)
            for r in sorted(range_readings, key=lambda r: r.day)
        ]
        day_factors = {r.day: factor_for_day(intervals, r.day) for r in range_readings}

        previous_year = self._build_previous_year(request, consumption, unit, intervals)
        trendline = None
        if request.with_trendline:
            horizon = int(self._settings.get("charts.trend_horizon", 30))
            trendline = build_trendline(consumption[Aggregation.DAILY], unit, horizon)

        kpi = compute_kpis(daily_points, range_readings, unit, intervals)

        self._logger.log(
            LogCategory.GUI,
            LogLevel.INFO,
            f"Dashboard {start} → {end} unit={unit.value}: "
            f"{len(daily_points)} daily point(s), "
            f"{'trendline on' if trendline else 'trendline off'}",
        )
        return Dashboard(
            unit=unit,
            meter_series=meter_series,
            consumption=consumption,
            previous_year=previous_year,
            trendline=trendline,
            kpi=kpi,
            table_rows=table_rows,
            day_factors=day_factors,
        )

    def _resolve_range(self, request: QueryRequest) -> tuple[date, date]:
        if request.start is not None and request.end is not None:
            return request.start, request.end
        all_readings = self._repo.get_readings(None, None) or []
        if all_readings:
            days = [r.day for r in all_readings]
            return min(days), max(days)
        end = self._clock.today()
        return end - timedelta(days=30), end

    def _build_previous_year(self, request, consumption, unit, intervals):
        if not request.include_previous_year:
            return None
        start, end = self._resolve_range(request)
        try:
            prev_start = start.replace(year=start.year - 1)
            prev_end = end.replace(year=end.year - 1)
        except ValueError:  # Feb 29
            prev_start = start.replace(year=start.year - 1, day=28)
            prev_end = end.replace(year=end.year - 1, day=28)
        prev_readings = self._repo.get_readings(prev_start - timedelta(days=1), prev_end)
        prev_points = consumption_series(prev_readings, prev_start, prev_end, unit, intervals)
        if not prev_points:
            return None
        prev_all = aggregate_all(prev_points)
        out: dict[Aggregation, list] = {}
        for agg in (Aggregation.DAILY, Aggregation.WEEKLY, Aggregation.MONTHLY):
            paired = previous_year_buckets(consumption[agg], prev_all[agg], agg)
            out[agg] = paired or []
        if not any(out.values()):
            return None
        return out
