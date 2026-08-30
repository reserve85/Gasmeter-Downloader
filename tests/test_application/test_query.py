"""Dashboard query use case tests: table rows, buckets, YoY, trendline, KPIs, unit."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.application.models import QueryRequest
from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import Aggregation, Source, ViewUnit
from app.domain.conversion import energy_kwh

from tests.conftest import FakeSettings, FixedClock


def _seed(fake_repo):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("104"))
    fake_repo.save_import(date(2025, 1, 2), Decimal("80"))
    fake_repo.save_import(date(2025, 1, 3), Decimal("82"))


def _use_case(fake_repo, gas_repo, logger, clock=None):
    return GetDashboardUseCase(fake_repo, gas_repo, FakeSettings(), logger, clock=clock)


def test_dashboard_default_range_and_rows(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(QueryRequest(start=None, end=None))

    assert len(dashboard.table_rows) == 5
    # newest day on top (owner: "order by desc")
    assert dashboard.table_rows[0][0] == date(2026, 1, 3)
    assert dashboard.table_rows[-1][0] == date(2025, 1, 2)
    # each row: date, import, interpolated, modified, source
    assert dashboard.table_rows[0][1] == Decimal("104")
    assert dashboard.table_rows[0][4] == Source.LOGFILE


def test_interval_filter_narrows_rows(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(start=date(2026, 1, 2), end=date(2026, 1, 3))
    )
    assert len(dashboard.table_rows) == 2
    assert dashboard.table_rows[0][0] == date(2026, 1, 3)  # newest first


def test_first_and_last_reading_day(fake_repo, gas_repo, logger):
    _seed(fake_repo)
    use_case = _use_case(fake_repo, gas_repo, logger)
    assert use_case.first_reading_day() == date(2025, 1, 2)
    assert use_case.last_reading_day() == date(2026, 1, 3)


def test_first_and_last_reading_day_empty(fake_repo, gas_repo, logger):
    use_case = _use_case(fake_repo, gas_repo, logger)
    assert use_case.first_reading_day() is None
    assert use_case.last_reading_day() is None


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


def _seed_year(fake_repo, start: str) -> None:
    """Five consecutive days starting at ``start`` with +2 m³/day deltas (100, 102, …)."""
    from datetime import timedelta

    first = date.fromisoformat(start)
    for offset in range(5):
        fake_repo.save_import(first + timedelta(days=offset), Decimal(100 + offset * 2))


def test_year_projection_in_kpi(fake_repo, gas_repo, logger):
    _seed_year(fake_repo, "2026-01-01")
    use_case = _use_case(fake_repo, gas_repo, logger, clock=FixedClock(date(2026, 1, 5)))
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            with_year_projection=True,
        )
    )
    kpi = dashboard.kpi
    # daily deltas Jan 2..5 = 8 m³ over 4 data days (avg 2/day);
    # remaining 360 days -> 8 + 720 = 728
    assert kpi.year_consumed == Decimal("8")
    assert kpi.year_projection == Decimal("728")
    assert kpi.projection_basis == "current-year"
    assert kpi.projection_year == 2026


def test_year_projection_falls_back_without_previous_data(fake_repo, gas_repo, logger):
    _seed_year(fake_repo, "2026-01-01")
    use_case = _use_case(fake_repo, gas_repo, logger, clock=FixedClock(date(2026, 1, 5)))
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            with_year_projection=True,
            project_by_previous_year=True,
        )
    )
    # no previous-year data exists -> projection basis defaults to the current year
    assert dashboard.kpi.projection_year == 2026
    assert dashboard.kpi.year_consumed == Decimal("8")
    assert dashboard.kpi.projection_basis == "current-year"


def test_year_projection_with_real_previous_data(fake_repo, gas_repo, logger):
    _seed_year(fake_repo, "2026-01-01")
    # fresh inserts for the previous year: +5 m³/day
    from datetime import timedelta

    for offset in range(5):
        fake_repo.save_import(
            date(2025, 1, 1) + timedelta(days=offset), Decimal(100 + offset * 5)
        )
    use_case = _use_case(fake_repo, gas_repo, logger, clock=FixedClock(date(2026, 1, 5)))
    dashboard = use_case.run(
        QueryRequest(
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            with_year_projection=True,
            project_by_previous_year=True,
        )
    )
    kpi = dashboard.kpi
    assert kpi.projection_basis == "previous-year"
    # prev daily avg = 5/day -> 8 + 5 * 360 = 1808
    assert kpi.year_projection == Decimal("1808")


def test_kwh_uses_the_interval_specific_factor(fake_repo, gas_repo, logger):
    """m³ must be converted per interval: different cal/z -> different kWh."""
    from app.domain.entities import GasParameterInterval

    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("104"))
    gas_repo.upsert_interval(
        GasParameterInterval(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 1, 2),
            calorific_value=Decimal("10.0"),
            z_value=Decimal("1.0"),
        )
    )
    gas_repo.upsert_interval(
        GasParameterInterval(
            valid_from=date(2026, 1, 3),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    use_case = _use_case(fake_repo, gas_repo, logger)
    dashboard = use_case.run(
        QueryRequest(start=date(2026, 1, 2), end=date(2026, 1, 3), unit=ViewUnit.KWH)
    )
    daily = dashboard.consumption[Aggregation.DAILY]
    # day 01-02 consumes 01-01→01-02 (2 m³) with factor 10.0*1.0 = 20.0 kWh
    # day 01-03 consumes 01-02→01-03 (2 m³) with factor 11.342*0.9589 ≈ 21.7 kWh
    assert daily[0].energy_kwh == Decimal("20.000")
    assert daily[1].energy_kwh == energy_kwh(Decimal("2"), Decimal("11.342"), Decimal("0.9589"))
