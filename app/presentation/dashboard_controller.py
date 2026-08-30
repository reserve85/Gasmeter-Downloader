"""Reactive dashboard controller - two independent scopes (table + charts).

The table scope filters by an explicit day range or a rolling preset, the charts
scope by whole years or a yearly preset. Any state change re-runs the local
GetDashboardUseCase for BOTH scopes and emits a per-scope signal, so the active
and the inactive tab are always consistent ("AJAX-like" refresh).

Presets store only the preset key; the concrete range is recomputed from
``today`` on every refresh. That never writes into the date-picker widgets and
makes rolling windows self-extending after imports.
"""

from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import QObject, pyqtSignal

from app.application.models import QueryRequest
from app.domain.entities import Aggregation, LogCategory, LogLevel, ViewUnit
from app.presentation.i18n import Translator


class _DefaultClock:
    def today(self) -> date:
        return date.today()


TABLE_PRESETS = ("all", "first_today", "30d", "90d", "year")
CHART_PRESETS = ("all", "this_year", "last_year", "last3")


class DashboardController(QObject):
    table_dashboard_changed = pyqtSignal(object)  # Dashboard (table scope)
    charts_dashboard_changed = pyqtSignal(object)  # Dashboard (charts scope)

    def __init__(self, query_use_case, settings, logger, tr: Translator, clock=None, parent=None):
        super().__init__(parent)
        self._use_case = query_use_case
        self._settings = settings
        self._logger = logger
        self._tr = tr
        self._clock = clock or _DefaultClock()

        default_unit = ViewUnit.M3 if str(settings.get("app.unit", "m³")) == "m³" else ViewUnit.KWH
        #: shared across both scopes
        self._unit = default_unit
        self._aggregation = Aggregation.DAILY
        self._include_previous_year = False
        self._with_trendline = False
        self._project_by_previous_year = False

        #: table scope (explicit range OR rolling preset)
        self._table_start: date | None = None
        self._table_end: date | None = None
        self._table_preset: str | None = None

        #: charts scope (explicit year range OR yearly preset)
        self._charts_start_year: int | None = None
        self._charts_end_year: int | None = None
        self._charts_preset: str | None = None

        #: concrete ranges applied by the last refresh - the single source of
        #: truth for the date pickers ("AJAX": presets must move the pickers).
        self._resolved_table_range: tuple[date | None, date | None] = (None, None)
        self._resolved_chart_range: tuple[date | None, date | None] = (None, None)

    # -- resolved-range accessors (picker sync) ---------------------------------
    def table_resolved_range(self) -> tuple[date | None, date | None]:
        """The ``(start, end)`` the table scope reads from on the last refresh."""
        return self._resolved_table_range

    def charts_resolved_years(self) -> tuple[int | None, int | None]:
        """``(from_year, to_year)`` applied to the charts scope (None = unlimited)."""
        start, end = self._resolved_chart_range
        if start is None or end is None:
            return None, None
        return start.year, end.year

    def table_preset(self) -> str | None:
        return self._table_preset

    def charts_preset(self) -> str | None:
        return self._charts_preset

    # -- shared state --------------------------------------------------------
    def set_unit(self, unit: ViewUnit) -> None:
        self._unit = unit
        self.refresh()

    def set_aggregation(self, agg: Aggregation) -> None:
        self._aggregation = agg
        self.refresh()

    def set_include_previous_year(self, enabled: bool) -> None:
        self._include_previous_year = enabled
        self.refresh()

    def set_trendline(self, enabled: bool) -> None:
        self._with_trendline = enabled
        self.refresh()

    def set_project_by_previous_year(self, enabled: bool) -> None:
        """Use the previous year's daily averages for the year projection."""
        self._project_by_previous_year = enabled
        self.refresh()

    # -- table scope ----------------------------------------------------------
    def set_table_range(self, start: date | None, end: date | None) -> None:
        self._table_start, self._table_end = start, end
        self._table_preset = None
        self.refresh()

    def apply_table_preset(self, preset: str) -> None:
        if preset not in TABLE_PRESETS:
            raise ValueError(f"Unknown table preset: {preset!r}")
        self._table_preset = preset
        self.refresh()

    def _resolve_table_range(self) -> tuple[date | None, date | None]:
        if self._table_preset is None:
            return self._table_start, self._table_end
        if self._table_preset == "all":
            return self._use_case.first_reading_day(), self._use_case.last_reading_day()
        today = self._clock.today()
        if self._table_preset == "first_today":
            return self._use_case.first_reading_day(), today
        if self._table_preset == "30d":
            return today - timedelta(days=30), today
        if self._table_preset == "90d":
            return today - timedelta(days=90), today
        if self._table_preset == "year":
            return today.replace(month=1, day=1), today
        return None, None

    # -- charts scope ---------------------------------------------------------
    def set_charts_years(self, start_year: int | None, end_year: int | None) -> None:
        self._charts_start_year, self._charts_end_year = start_year, end_year
        self._charts_preset = None
        self.refresh()

    def apply_charts_preset(self, preset: str) -> None:
        if preset not in CHART_PRESETS:
            raise ValueError(f"Unknown charts preset: {preset!r}")
        self._charts_preset = preset
        self.refresh()

    def _resolve_charts_range(self) -> tuple[date | None, date | None]:
        if self._charts_preset is None:
            if self._charts_start_year is not None and self._charts_end_year is not None:
                return date(self._charts_start_year, 1, 1), date(self._charts_end_year, 12, 31)
            return None, None
        if self._charts_preset == "all":
            return self._use_case.first_reading_day(), self._use_case.last_reading_day()
        today = self._clock.today()
        if self._charts_preset == "this_year":
            return date(today.year, 1, 1), date(today.year, 12, 31)
        if self._charts_preset == "last_year":
            return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        if self._charts_preset == "last3":
            return date(today.year - 2, 1, 1), date(today.year, 12, 31)
        return None, None

    # -- refresh ----------------------------------------------------------------
    def refresh(self) -> None:
        table_start, table_end = self._resolve_table_range()
        charts_start, charts_end = self._resolve_charts_range()
        self._resolved_table_range = (table_start, table_end)
        self._resolved_chart_range = (charts_start, charts_end)
        self._emit(
            self.table_dashboard_changed,
            QueryRequest(
                start=table_start,
                end=table_end,
                unit=self._unit,
                aggregation=Aggregation.DAILY,
                include_previous_year=False,
                with_trendline=False,
                with_year_projection=False,
                project_by_previous_year=False,
            ),
        )
        self._emit(
            self.charts_dashboard_changed,
            QueryRequest(
                start=charts_start,
                end=charts_end,
                unit=self._unit,
                aggregation=self._aggregation,
                include_previous_year=self._include_previous_year,
                with_trendline=self._with_trendline,
                with_year_projection=True,
                project_by_previous_year=self._project_by_previous_year,
            ),
        )

    def _emit(self, signal_: pyqtSignal, request: QueryRequest) -> None:
        try:
            dashboard = self._use_case.run(request)
        except Exception as exc:  # noqa: BLE001
            self._logger.log(LogCategory.ERROR, LogLevel.ERROR, f"Dashboard refresh failed: {exc}")
            return
        signal_.emit(dashboard)
