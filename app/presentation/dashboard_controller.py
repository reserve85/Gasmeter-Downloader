"""Reactive dashboard controller - single source of truth for the view state.

Every state change re-runs the local GetDashboardUseCase and emits
``dashboard_changed(Dashboard)``; the table model and all chart cards are
slot-connected and repaint immediately ("AJAX-like" refresh). No network or
disk access happens here.
"""

from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import QObject, pyqtSignal

from app.application.models import QueryRequest
from app.domain.entities import Aggregation, LogCategory, LogLevel, ViewUnit
from app.presentation.i18n import Translator


class DashboardController(QObject):
    dashboard_changed = pyqtSignal(object)  # Dashboard
    progress = pyqtSignal(str)

    def __init__(self, query_use_case, settings, logger, tr: Translator, parent: QObject | None = None):
        super().__init__(parent)
        self._use_case = query_use_case
        self._settings = settings
        self._logger = logger
        self._tr = tr
        default_unit = ViewUnit.M3 if str(settings.get("app.unit", "m³")) == "m³" else ViewUnit.KWH
        self._request = QueryRequest(
            start=None,
            end=None,
            unit=default_unit,
            aggregation=Aggregation.DAILY,
            include_previous_year=False,
            with_trendline=False,
        )

    # -- public API -------------------------------------------------------------
    def set_date_range(self, start: date | None, end: date | None) -> None:
        self._request = QueryRequest(
            start=start, end=end, unit=self._request.unit, aggregation=self._request.aggregation,
            include_previous_year=self._request.include_previous_year,
            with_trendline=self._request.with_trendline,
        )
        self.refresh()

    def set_unit(self, unit: ViewUnit) -> None:
        self._request = QueryRequest(
            start=self._request.start, end=self._request.end, unit=unit, aggregation=self._request.aggregation,
            include_previous_year=self._request.include_previous_year,
            with_trendline=self._request.with_trendline,
        )
        self.refresh()

    def set_aggregation(self, agg: Aggregation) -> None:
        self._request = QueryRequest(
            start=self._request.start, end=self._request.end, unit=self._request.unit, aggregation=agg,
            include_previous_year=self._request.include_previous_year,
            with_trendline=self._request.with_trendline,
        )
        self.refresh()

    def set_include_previous_year(self, enabled: bool) -> None:
        self._request = QueryRequest(
            start=self._request.start, end=self._request.end, unit=self._request.unit,
            aggregation=self._request.aggregation, include_previous_year=enabled,
            with_trendline=self._request.with_trendline,
        )
        self.refresh()

    def set_trendline(self, enabled: bool) -> None:
        self._request = QueryRequest(
            start=self._request.start, end=self._request.end, unit=self._request.unit,
            aggregation=self._request.aggregation, include_previous_year=self._request.include_previous_year,
            with_trendline=enabled,
        )
        self.refresh()

    def refresh(self) -> None:
        try:
            dashboard = self._use_case.run(self._request)
        except Exception as exc:  # noqa: BLE001
            self._logger.log(LogCategory.ERROR, LogLevel.ERROR, f"Dashboard refresh failed: {exc}")
            return
        self.dashboard_changed.emit(dashboard)

    def apply_preset(self, preset: str, today: date | None = None) -> None:
        today = today or date.today()
        presets = {
            "all": (None, None),
            "30d": (today - timedelta(days=30), today),
            "90d": (today - timedelta(days=90), today),
            "year": (today.replace(month=1, day=1), today),
        }
        start, end = presets.get(preset, (None, None))
        self.set_date_range(start, end)

    @property
    def request(self) -> QueryRequest:
        return self._request
