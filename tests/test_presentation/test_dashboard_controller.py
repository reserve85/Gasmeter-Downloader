"""DashboardController tests: per-scope setters emit matching dashboards.

Core requirement #5: a rolling preset is stored as a key and resolved at
refresh time — it never writes into any date-picker widget, and the window
moves automatically when the clock advances.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import ViewUnit
from app.presentation.dashboard_controller import DashboardController
from app.presentation.i18n import Translator

from tests.conftest import FakeSettings, FixedClock, RecordingLogger


def _seed(fake_repo):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2025, 12, 15), Decimal("90"))
    fake_repo.save_import(date(2025, 12, 16), Decimal("92"))
    fake_repo.save_import(date(2026, 2, 3), Decimal("110"))
    fake_repo.save_import(date(2026, 2, 4), Decimal("112"))


def _controller(fake_repo, gas_repo, logger, today=None):
    use_case = GetDashboardUseCase(fake_repo, gas_repo, FakeSettings({"app.unit": "m³"}), logger)
    return DashboardController(
        use_case,
        FakeSettings({"app.unit": "m³"}),
        logger,
        Translator("en"),
        clock=FixedClock(today or date(2026, 1, 5)),
    )


def test_refresh_emits_both_scopes(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger())
    table_emitted, charts_emitted = [], []
    controller.table_dashboard_changed.connect(table_emitted.append)
    controller.charts_dashboard_changed.connect(charts_emitted.append)
    controller.refresh()
    assert len(table_emitted) == 1
    assert len(charts_emitted) == 1
    assert table_emitted[0].table_rows
    assert charts_emitted[0].table_rows


def test_set_table_range_clears_preset(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger())
    controller.apply_table_preset("30d")
    assert controller._table_preset == "30d"  # noqa: SLF001
    controller.set_table_range(date(2025, 12, 15), date(2025, 12, 16))
    assert controller._table_preset is None  # noqa: SLF001


def test_table_preset_dynamic_window(qapp, fake_repo, gas_repo):
    """A rolling preset moves with the clock and never touches the pickers."""
    _seed(fake_repo)
    logger = RecordingLogger()
    controller = _controller(fake_repo, gas_repo, logger, today=date(2026, 1, 5))
    emitted = []
    controller.table_dashboard_changed.connect(emitted.append)
    controller.apply_table_preset("30d")
    first_dashboard = emitted[-1]
    assert first_dashboard.table_rows  # data within Dec 7 2025 .. Jan 5 2026

    # advance the clock -> the same preset covers a later window
    controller._clock.set(date(2026, 2, 4))  # noqa: SLF001
    controller.refresh()
    second_dashboard = emitted[-1]
    assert second_dashboard.table_rows != first_dashboard.table_rows
    latest = max(row[0] for row in second_dashboard.table_rows)
    assert latest <= date(2026, 2, 4)


def test_charts_years_explicit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger())
    emitted = []
    controller.charts_dashboard_changed.connect(emitted.append)
    controller.set_charts_years(2025, 2026)
    dashboard = emitted[-1]
    years = {row[0].year for row in dashboard.table_rows}
    assert years == {2025, 2026}


def test_charts_preset_this_year(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 1, 5))
    emitted = []
    controller.charts_dashboard_changed.connect(emitted.append)
    controller.apply_charts_preset("this_year")
    dashboard = emitted[-1]
    years = {row[0].year for row in dashboard.table_rows}
    assert years == {2026}


def test_charts_preset_last3(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 1, 5))
    emitted = []
    controller.charts_dashboard_changed.connect(emitted.append)
    controller.apply_charts_preset("last3")
    dashboard = emitted[-1]
    assert dashboard.kpi.projection_year == 2026  # projection targets the end year


def test_charts_projection_always_enabled_for_charts_scope(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger())
    emitted = []
    controller.charts_dashboard_changed.connect(emitted.append)
    controller.set_charts_years(2025, 2026)
    dashboard = emitted[-1]
    assert dashboard.kpi.projection_year == 2026
    assert dashboard.kpi.projection_basis in ("current-year", "previous-year", "")


def test_set_unit_emits_both_scopes(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger())
    table_emitted, charts_emitted = [], []
    controller.table_dashboard_changed.connect(table_emitted.append)
    controller.charts_dashboard_changed.connect(charts_emitted.append)
    controller.set_unit(ViewUnit.KWH)
    assert table_emitted and table_emitted[-1].unit == ViewUnit.KWH
    assert charts_emitted and charts_emitted[-1].unit == ViewUnit.KWH


def test_unknown_presets_rejected(qapp, fake_repo, gas_repo):
    controller = _controller(fake_repo, gas_repo, RecordingLogger())

    with pytest.raises(ValueError):
        controller.apply_table_preset("bogus")
    with pytest.raises(ValueError):
        controller.apply_charts_preset("bogus")


def test_table_preset_first_today(qapp, fake_repo, gas_repo):
    """Default table filter: from the first DB entry to today."""
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 2, 5))
    emitted = []
    controller.table_dashboard_changed.connect(emitted.append)
    controller.apply_table_preset("first_today")
    dashboard = emitted[-1]
    days = [row[0] for row in dashboard.table_rows]
    assert min(days) == date(2025, 12, 15)  # earliest seeded day
    assert max(days) <= date(2026, 2, 5)
    assert controller.table_resolved_range() == (date(2025, 12, 15), date(2026, 2, 5))
    assert controller.table_preset() == "first_today"


def test_table_first_today_advances_with_clock(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 1, 5))
    controller.apply_table_preset("first_today")
    assert controller.table_resolved_range()[1] == date(2026, 1, 5)
    controller._clock.set(date(2026, 3, 1))  # noqa: SLF001
    controller.refresh()
    assert controller.table_resolved_range() == (date(2025, 12, 15), date(2026, 3, 1))


def test_charts_resolved_years_exposed(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 1, 5))
    controller.apply_charts_preset("last3")
    assert controller.charts_resolved_years() == (2024, 2026)
    assert controller.charts_preset() == "last3"
    # "all" resolves to the actual data range -> the pickers show the truth
    controller.apply_charts_preset("all")
    assert controller.charts_resolved_years() == (2025, 2026)


def test_explicit_charts_years_clears_preset_and_exposes(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(fake_repo, gas_repo, RecordingLogger(), today=date(2026, 1, 5))
    controller.apply_charts_preset("this_year")
    controller.set_charts_years(2025, 2026)
    assert controller.charts_preset() is None
    assert controller.charts_resolved_years() == (2025, 2026)
