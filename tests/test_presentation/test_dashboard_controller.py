"""DashboardController tests: every setter emits dashboard_changed and re-queries."""

from __future__ import annotations

from datetime import date


from app.application.models import QueryRequest
from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import Aggregation, ViewUnit
from app.presentation.dashboard_controller import DashboardController
from app.presentation.i18n import Translator

from tests.conftest import FakeSettings, RecordingLogger


def _controller(qapp, fake_repo, gas_repo):
    logger = RecordingLogger()
    use_case = GetDashboardUseCase(fake_repo, gas_repo, FakeSettings({"app.unit": "m³"}), logger)
    return DashboardController(use_case, FakeSettings({"app.unit": "m³"}), logger, Translator("en"))


def _seed(fake_repo):
    from decimal import Decimal

    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))


def test_refresh_emits_dashboard(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    emitted = []
    controller.dashboard_changed.connect(emitted.append)
    controller.refresh()
    assert len(emitted) == 1
    assert emitted[0].table_rows


def test_set_unit_emits(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    emitted = []
    controller.dashboard_changed.connect(emitted.append)
    controller.set_unit(ViewUnit.KWH)
    assert emitted and emitted[-1].unit == ViewUnit.KWH


def test_set_aggregation_emits(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    emitted = []
    controller.dashboard_changed.connect(emitted.append)
    controller.set_aggregation(Aggregation.MONTHLY)
    assert emitted and emitted[-1].consumption[Aggregation.MONTHLY]


def test_set_date_range_and_toggles_emit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    emitted = []
    controller.dashboard_changed.connect(emitted.append)
    controller.set_date_range(date(2026, 1, 1), date(2026, 1, 2))
    controller.set_include_previous_year(True)
    controller.set_trendline(True)
    assert len(emitted) == 3


def test_apply_preset(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    emitted = []
    controller.dashboard_changed.connect(emitted.append)
    controller.apply_preset("30d")
    assert emitted and emitted[-1].table_rows is not None


def test_request_properties_updated(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    controller = _controller(qapp, fake_repo, gas_repo)
    controller.set_unit(ViewUnit.KWH)
    controller.set_trendline(True)
    request: QueryRequest = controller.request
    assert request.unit == ViewUnit.KWH
    assert request.with_trendline is True
