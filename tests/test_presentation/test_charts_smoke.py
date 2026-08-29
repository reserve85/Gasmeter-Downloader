"""ChartsTab smoke tests (offscreen): build, switch unit/agg, toggles, theme."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.application.models import QueryRequest
from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import ViewUnit
from app.presentation.charts import ChartsTab
from app.presentation.i18n import Translator

from tests.conftest import FakeSettings, RecordingLogger


def _seed(fake_repo):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("105"))
    fake_repo.save_import(date(2025, 1, 2), Decimal("80"))
    fake_repo.save_import(date(2025, 1, 3), Decimal("83"))


def _dashboard(fake_repo, gas_repo, logger):
    use_case = GetDashboardUseCase(fake_repo, gas_repo, FakeSettings(), logger)
    return use_case.run(
        QueryRequest(
            start=date(2026, 1, 1),
            end=date(2026, 1, 3),
            unit=ViewUnit.M3,
            include_previous_year=True,
            with_trendline=True,
        )
    )


def test_charts_tab_builds_and_renders(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    logger = RecordingLogger()
    dashboard = _dashboard(fake_repo, gas_repo, logger)
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    assert tab._meter_view is not None  # noqa: SLF001
    assert tab._usage_view is not None  # noqa: SLF001
    assert tab._monthly_view is not None  # noqa: SLF001


def test_charts_tab_switch_aggregation_unit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    logger = RecordingLogger()
    dashboard = _dashboard(fake_repo, gas_repo, logger)
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)

    tab._agg.setCurrentIndex(2)  # monthly  # noqa: SLF001
    tab._render()  # noqa: SLF001
    tab._unit.setCurrentIndex(1)  # kWh  # noqa: SLF001
    tab._render()  # noqa: SLF001
    # no exceptions raised


def test_charts_tab_toggles_yoy_and_trend(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    logger = RecordingLogger()
    dashboard = _dashboard(fake_repo, gas_repo, logger)
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)

    tab._yoy.setChecked(True)  # noqa: SLF001
    tab._trend.setChecked(True)  # noqa: SLF001
    tab._render()  # noqa: SLF001
    assert dashboard.previous_year is not None
    assert dashboard.trendline is not None


def test_charts_tab_theme_change(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    logger = RecordingLogger()
    dashboard = _dashboard(fake_repo, gas_repo, logger)
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    tab.apply_theme(True)  # dark
    assert tab._dark is True  # noqa: SLF001


def test_charts_tab_empty_state(qapp, fake_repo, gas_repo):
    logger = RecordingLogger()
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(_dashboard(fake_repo, gas_repo, logger))  # empty dataset renders fine
    assert tab._empty_label is not None  # noqa: SLF001
