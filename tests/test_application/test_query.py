"""Dashboard query use case tests: table rows, buckets, YoY, trendline, KPIs, unit."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.application.models import QueryRequest
from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import Aggregation, Source, ViewUnit
from app.domain.conversion import energy_kwh

from tests.conftest import FakeSettings


def _seed(fake_repo):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("104"))
    fake_repo.save_import(date(2025, 1, 2), Decimal("80"))
    fake_repo.save_import(date(2025, 1, 3), Decimal("82"))


def _use_case(fake_repo, gas_repo, logger):
    return GetDashboardUseCase(fake_repo, gas_repo, FakeSettings(), logger)


def test_dashboard_default_range_and_rows(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(QueryRequest(start=None, end=None))

    assert len(dashboard.table_rows) == 5
    assert dashboard.table_rows[0][0] == date(2025, 1, 2)
    assert dashboard.table_rows[-1][0] == date(2026, 1, 3)
    # each row: date, import, interpolated, modified, source
    assert dashboard.table_rows[-1][1] == Decimal("104")
    assert dashboard.table_rows[-1][4] == Source.LOGFILE


def test_interval_filter_narrows_rows(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(start=date(2026, 1, 2), end=date(2026, 1, 3))
    )
    assert len(dashboard.table_rows) == 2
    assert dashboard.table_rows[0][0] == date(2026, 1, 2)


def test_daily_buckets_and_unit_conversion(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 2), end=date(2026, 1, 3), unit=ViewUnit.M3
        )
    )
    daily = dashboard.consumption[Aggregation.DAILY]
    assert len(daily) == 2
    # first plotted day (2026-01-02) consumes 2026-01-01
    assert daily[0].volume_m3 == Decimal("2")
    assert daily[1].volume_m3 == Decimal("2")

    kwh_dashboard = use_case.run(
        QueryRequest(start=date(2026, 1, 2), end=date(2026, 1, 3), unit=ViewUnit.KWH)
    )
    expected = energy_kwh(Decimal("2"), Decimal("11.342"), Decimal("0.9589"))
    assert kwh_dashboard.consumption[Aggregation.DAILY][0].energy_kwh == expected
    assert kwh_dashboard.kpi.total_energy == 2 * expected


def test_previous_year_overlay(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 2), end=date(2026, 1, 3),
            include_previous_year=True,
        )
    )
    assert dashboard.previous_year is not None
    prev_daily = dashboard.previous_year[Aggregation.DAILY]
    # prev-year daily for 2025-01-02..03 from readings 2025-01-03/04
    assert prev_daily and prev_daily[0].volume_m3 == Decimal("2")


def test_trendline_present_when_requested(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 1), end=date(2026, 1, 3), with_trendline=True
        )
    )
    assert dashboard.trendline is not None
    # fitted range + projection
    assert len(dashboard.trendline.series.points) > 3


def test_kpi_latest_and_interpolated_count(fake_repo, gas_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("130"))
    from app.application.use_cases.interpolate import RecomputeInterpolationUseCase

    RecomputeInterpolationUseCase(fake_repo, logger).run()
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(start=date(2026, 1, 1), end=date(2026, 1, 3))
    )
    assert dashboard.kpi.interpolated_days_in_range == 1
    assert dashboard.kpi.latest_meter_value == Decimal("130")


def test_empty_database_returns_empty_dashboard(fake_repo, gas_repo, logger):
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(QueryRequest(start=None, end=None))
    assert dashboard.table_rows == []
    assert dashboard.meter_series == []
    assert dashboard.previous_year is None
    assert dashboard.trendline is None
