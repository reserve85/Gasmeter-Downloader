"""Charts tab - grid card dashboard (yearly filter, lines, tooltips, big view).

Every chart card owns a *builder callable* returning a fresh ``MplRender``; the
"Show in big" dialog re-renders the same builder at a larger window size. Cards
re-theme by rebuilding. All rendering happens in Matplotlib (``mpl_charts``);
Qt provides only the widget shell. The tab consumes a single precomputed
`Dashboard`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain.conversion import point_value
from app.domain.entities import Aggregation, Dashboard, ViewUnit
from app.presentation.i18n import Translator
from app.presentation.mpl_charts import (
    MplChartCanvas,
    MplRender,
    _HoverTarget,
    _SERIES_COLOR,
    _TREND_COLOR,
    _add_datetime_axes,
    _bar_tolerances,
    _bar_value_labels,
    _date2num,
    _line_tolerances,
    _make_canvas,
    _style_axes,
    _tooltip_text,
)

_CHART_MIN_HEIGHT = 180  # auto-scaled cards (requirement: fit on one page)


# -- hover targets ----------------------------------------------------------------
def _meter_targets(points, daily_by_day: dict, tr: Translator, base: float = 0.0) -> tuple[list[_HoverTarget], tuple[float, float]]:
    """Hover targets for the meter line (one per point) + snap tolerances.

    ``base`` is the normalization offset so the targets line up with the
    drawn series (which starts at 0).
    """
    targets = [
        _HoverTarget(
            _date2num(point.day),
            float(point.display_value) - base,
            _tooltip_text(
                point.day,
                point.adjusted_value,
                delta.volume_m3 if (delta := daily_by_day.get(point.day)) else Decimal("0"),
                delta.energy_kwh if delta else Decimal("0"),
                tr,
            ),
        )
        for point in points
    ]
    xs = [_date2num(point.day) for point in points]
    ys = [float(point.display_value) - base for point in points]
    return targets, _line_tolerances(xs, ys)


def _usage_targets(points, meter_by_day: dict, unit: ViewUnit, tr: Translator) -> tuple[list[_HoverTarget], tuple[float, float]]:
    """Hover targets for the usage line (one per bucket) + snap tolerances."""
    targets = [
        _HoverTarget(
            _date2num(point.day),
            float(point_value(point, unit)),
            _tooltip_text(
                point.day,
                meter.adjusted_value if (meter := meter_by_day.get(point.day)) else Decimal("0"),
                point.volume_m3,
                point.energy_kwh,
                tr,
            ),
        )
        for point in points
    ]
    xs = [_date2num(point.day) for point in points]
    ys = [float(point_value(point, unit)) for point in points]
    return targets, _line_tolerances(xs, ys)


# -- chart builders (each returns a fresh MplRender) -------------------------------
def _meter_chart_builder(points, daily, dark: bool, tr: Translator):
    """Cumulative meter line starting at 0 - no dashed overlay.

    The absolute meter value differs per range by offset; the line is
    normalized so it starts at 0 and counts up by the daily consumption
    (exactly like the per-year comparison). The tooltip still shows the
    absolute meter value of that day.
    """
    daily_by_day = {p.day: p for p in daily}
    base = float(points[0].display_value) if points else 0.0
    targets, (x_tol, y_tol) = _meter_targets(points, daily_by_day, tr, base=base)

    def build() -> MplRender:
        def draw(ax) -> None:
            _add_datetime_axes(ax, [p.day for p in points], fmt="%Y-%m", dark=dark)
            if not points:
                return
            ax.plot(
                [_date2num(p.day) for p in points],
                [float(p.display_value) - base for p in points],
                color=_SERIES_COLOR,
                marker="o",
                markersize=3,
                linewidth=1.5,
                label=tr.t("charts.meter.title"),
            )
            ax.legend(loc="best", fontsize=8, frameon=False)

        return MplRender(draw=draw, targets=targets, x_tol=x_tol, y_tol=y_tol)

    return build


def _usage_chart_builder(dashboard: Dashboard, agg: Aggregation, trend_on: bool, dark: bool, tr: Translator):
    """Daily/weekly/monthly usage as a line chart with points.

    The previous-year overlay lives in the dedicated comparison tab; the trend
    line stays an opt-in dashed overlay.
    """
    unit = dashboard.unit
    points = dashboard.consumption.get(agg, [])
    meter_by_day = {p.day: p for p in dashboard.meter_series}
    x_format = "%m/%Y" if agg != Aggregation.DAILY else "%Y-%m-%d"
    targets, (x_tol, y_tol) = _usage_targets(points, meter_by_day, unit, tr)

    def build() -> MplRender:
        def draw(ax) -> None:
            axis_days = [p.day for p in points]
            if points:
                ax.plot(
                    [_date2num(p.day) for p in points],
                    [float(point_value(p, unit)) for p in points],
                    color=_SERIES_COLOR,
                    marker="o",
                    markersize=3,
                    linewidth=1.5,
                    label=tr.t("charts.usage.title"),
                )
            if trend_on and dashboard.trendline is not None:
                trend_points = dashboard.trendline.series.points
                ax.plot(
                    [_date2num(p.day) for p in trend_points],
                    [float(point_value(p, unit)) for p in trend_points],
                    color=_TREND_COLOR,
                    linestyle="--",
                    linewidth=1.2,
                    label=tr.t("charts.trend"),
                )
                axis_days = axis_days + [p.day for p in trend_points]
            if points or (trend_on and dashboard.trendline is not None):
                ax.legend(loc="best", fontsize=8, frameon=False)
            _add_datetime_axes(ax, axis_days, fmt=x_format, dark=dark)

        return MplRender(draw=draw, targets=targets, x_tol=x_tol, y_tol=y_tol)

    return build


def _monthly_chart_builder(dashboard: Dashboard, dark: bool, tr: Translator):
    """Monthly block diagram - x axis MM/YYYY with integer value labels."""
    unit = dashboard.unit
    monthly = dashboard.consumption.get(Aggregation.MONTHLY, [])
    labels = [p.day.strftime("%m/%Y") for p in monthly]
    values = [float(point_value(point, unit)) for point in monthly]
    y_tol = _bar_tolerances(values)
    targets = [
        _HoverTarget(
            float(index),
            values[index],
            _tooltip_text(point.day, Decimal("0"), point.volume_m3, point.energy_kwh, tr, monthly=True),
        )
        for index, point in enumerate(monthly)
    ]

    def build() -> MplRender:
        def draw(ax) -> None:
            _style_axes(ax, dark)
            if not monthly:
                return
            xs = list(range(len(monthly)))
            bars = ax.bar(xs, values, width=0.8, color=_SERIES_COLOR, edgecolor="none")
            ax.set_xticks(xs)
            ax.set_xticklabels(labels, fontsize=8)
            ax.set_xlim(-0.5, len(monthly) - 0.5)
            ax.margins(y=0.15)
            _bar_value_labels(ax, bars, unit.value, dark, tr)

        return MplRender(draw=draw, targets=targets, x_tol=0.5, y_tol=y_tol, bar_hit=True)

    return build


# -- cards -------------------------------------------------------------------------
class ChartCard(QWidget):
    """Flat container matching the Compare tab: just a resizable chart canvas.

    No title bar or frame (the owner wants the chart formatting identical to
    the Compare page). Double-clicking the chart re-opens it in the enlarged
    "Show in big" dialog.
    """

    def __init__(self, title: str, tr: Translator, dark: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self._tr = tr
        self._dark = dark
        self._builder = None
        self._title = title

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.view = _make_canvas(self, min_height=_CHART_MIN_HEIGHT)
        self.view.set_double_click_callback(self._open_big)
        root.addWidget(self.view, 1)

    def set_chart(self, builder, title: str | None = None) -> None:
        """Store ``builder`` (-> ``MplRender``) and render it once."""
        self._builder = builder
        if title:
            self._title = title
        self.view.store_interaction(builder())

    def retranslate(self) -> None:
        """Nothing static to re-translate since the header was removed."""

    def _open_big(self) -> None:
        if self._builder is None:
            return
        dialog = BigChartDialog(self._builder(), self._title, self._dark, self)
        dialog.exec()


class BigChartDialog(QDialog):
    """Modal, resizable window showing a chart (requirement #11, maximizable)."""

    def __init__(self, render: MplRender, title: str, dark: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # maximizable + resizable via the title bar / size grip
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.resize(1000, 600)
        self.setSizeGripEnabled(True)
        layout = QVBoxLayout(self)
        view = _make_canvas(self, min_height=0)
        view.store_interaction(render)
        layout.addWidget(view)


class KpiCard(QWidget):
    """Flat overview card: KPI cells with unit suffixes + year projection."""

    def __init__(self, tr: Translator, dark: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self._tr = tr
        self._dark = dark
        self._grid = QGridLayout(self)
        self._cells: list[tuple[QLabel, QLabel]] = []

    def render(self, dashboard: Dashboard) -> None:
        tr = self._tr
        kpi = dashboard.kpi
        unit = dashboard.unit.value

        def value(text: str) -> QLabel:
            label = QLabel(text)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return label

        basis = ""
        if kpi.projection_basis == "previous-year":
            basis = f" ({tr.t('charts.projection.basis_prev')})"
        elif kpi.projection_basis == "current-year":
            basis = f" ({tr.t('charts.projection.basis_current')})"

        max_day_text = (
            tr.format_date(kpi.max_day.day) + " · " + tr.format_number(point_value(kpi.max_day, dashboard.unit)) + f" {unit}"
            if kpi.max_day
            else "–"
        )
        entries: list[tuple[str, str]] = [
            (tr.t("charts.kpi.total"), f"{tr.format_number(kpi.total_energy)} {unit}"),
            (tr.t("charts.kpi.avg_day"), f"{tr.format_number(kpi.average_per_day)} {unit}"),
            (tr.t("charts.kpi.max_day"), max_day_text),
            (tr.t("charts.kpi.interpolated"), str(kpi.interpolated_days_in_range)),
            (tr.t("charts.kpi.latest"), f"{tr.format_number(kpi.latest_meter_value)} {unit}"),
            (tr.t("charts.kpi.year_consumed"), f"{tr.format_number(kpi.year_consumed)} {unit}"),
            (tr.t("charts.kpi.projection"), f"{tr.format_number(kpi.year_projection)} {unit}{basis}"),
        ]
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for column, (label_text, value_text) in enumerate(entries):
            title = QLabel(label_text)
            title.setStyleSheet("font-weight: bold;")
            cell_value = value(value_text)
            self._grid.addWidget(title, 0, column)
            self._grid.addWidget(cell_value, 1, column)
        for column in range(len(entries)):
            self._grid.setColumnStretch(column, 1)


# -- ChartsTab ----------------------------------------------------------------------
class ChartsTab(QWidget):
    """Auto-scaled card dashboard with a yearly filter (requirements #8 + fit-one-page)."""

    def __init__(self, tr: Translator, dark: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._tr = tr
        self._dark = dark
        self._dashboard: Dashboard | None = None
        self._controller = None
        self._aggregations = {
            Aggregation.DAILY: tr.t("charts.agg.daily"),
            Aggregation.WEEKLY: tr.t("charts.agg.weekly"),
            Aggregation.MONTHLY: tr.t("charts.agg.monthly"),
        }
        self._units = {ViewUnit.M3: tr.t("charts.unit_m3"), ViewUnit.KWH: tr.t("charts.unit_kwh")}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._build_controls())

        # requirement: all charts fit one page and scale with the window -> a
        # grid (no scroll area) whose rows/columns stretch equally.
        self._cards = QGridLayout()
        self._cards.setContentsMargins(0, 0, 0, 0)
        self._cards.setSpacing(6)
        self._empty_label = QLabel(tr.t("charts.empty"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cards.addWidget(self._empty_label, 0, 0, 1, 2)
        root.addLayout(self._cards, 1)

        self._kpi_card: KpiCard | None = None
        self._meter_card: ChartCard | None = None
        self._usage_card: ChartCard | None = None
        self._monthly_card: ChartCard | None = None
        self._meter_view: MplChartCanvas | None = None
        self._usage_view: MplChartCanvas | None = None
        self._monthly_view: MplChartCanvas | None = None

        self._cards.setColumnStretch(0, 1)
        self._cards.setColumnStretch(1, 1)
        self._cards.setRowStretch(2, 1)
        self._cards.setRowStretch(3, 1)

    # -- controls ------------------------------------------------------------------
    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        now = date.today()

        self._year_from = QSpinBox()
        self._year_from.setRange(1990, 2100)
        self._year_from.setValue(now.year)
        self._year_to = QSpinBox()
        self._year_to.setRange(1990, 2100)
        self._year_to.setValue(now.year)

        self._preset = QComboBox()
        self._preset.addItem(self._tr.t("table.filter_custom"), None)
        for key, label in (
            ("all", "table.filter_all"),
            ("this_year", "charts.preset_this_year"),
            ("last_year", "charts.preset_last_year"),
            ("last3", "charts.preset_last3"),
        ):
            self._preset.addItem(self._tr.t(label), key)
        # the current year is the default chart view (owner: no full history).
        self._preset.setCurrentIndex(self._preset.findData("this_year"))

        self._agg = QComboBox()
        for agg, label in self._aggregations.items():
            self._agg.addItem(label, agg)
        self._unit = QComboBox()
        for unit, label in self._units.items():
            self._unit.addItem(label, unit)
        self._trend = QCheckBox(self._tr.t("charts.trend"))
        self._proj_prev = QCheckBox(self._tr.t("charts.projection_prev"))

        self._year_from_label = QLabel(self._tr.t("charts.year_from"))
        self._year_to_label = QLabel(self._tr.t("charts.year_to"))
        row.addWidget(self._year_from_label)
        row.addWidget(self._year_from)
        row.addWidget(self._year_to_label)
        row.addWidget(self._year_to)
        row.addWidget(self._preset)
        row.addWidget(self._agg)
        row.addWidget(self._unit)
        row.addWidget(self._trend)
        row.addWidget(self._proj_prev)
        row.addStretch(1)

        self._preset.currentIndexChanged.connect(self._on_preset)
        self._year_from.valueChanged.connect(self._on_year_changed)
        self._year_to.valueChanged.connect(self._on_year_changed)
        self._agg.currentIndexChanged.connect(self._on_agg)
        self._unit.currentIndexChanged.connect(self._on_unit)
        self._trend.toggled.connect(self._on_trend)
        self._proj_prev.toggled.connect(self._on_proj_prev)
        return row


# -- controller wiring ----------------------------------------------------------
    def bind(self, controller) -> None:
        self._controller = controller
        controller.charts_dashboard_changed.connect(self.set_dashboard)
        self._apply_initial_preset()

    def _apply_initial_preset(self) -> None:
        """Start on the current year instead of the whole history."""
        controller = self._controller_or_none()
        if controller is not None:
            controller.apply_charts_preset("this_year")

    def set_dashboard(self, dashboard: Dashboard) -> None:
        self._dashboard = dashboard
        index = self._unit.findData(dashboard.unit)
        if index >= 0 and index != self._unit.currentIndex():
            self._unit.blockSignals(True)
            self._unit.setCurrentIndex(index)
            self._unit.blockSignals(False)
        self._render()
        self._sync_year_pickers()

    def _sync_year_pickers(self) -> None:
        """Mirror the controller's resolved window into the year spinboxes (AJAX).

        Presets must visibly move the date pickers; programmatic updates use
        ``blockSignals`` so no refresh round-trip is triggered.
        """
        controller = self._controller_or_none()
        if controller is None:
            return
        from_year, to_year = controller.charts_resolved_years()
        if from_year is not None and to_year is not None:
            for spin, year in ((self._year_from, from_year), (self._year_to, to_year)):
                if spin.value() != year:
                    spin.blockSignals(True)
                    spin.setValue(year)
                    spin.blockSignals(False)
        self._preset.blockSignals(True)
        index = self._preset.findData(controller.charts_preset())
        self._preset.setCurrentIndex(index if index >= 0 else self._preset.findData(None))
        self._preset.blockSignals(False)

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._render()

    def apply_language(self) -> None:
        """Re-translate every static control after a language change."""
        self._aggregations = {
            Aggregation.DAILY: self._tr.t("charts.agg.daily"),
            Aggregation.WEEKLY: self._tr.t("charts.agg.weekly"),
            Aggregation.MONTHLY: self._tr.t("charts.agg.monthly"),
        }
        self._units = {ViewUnit.M3: self._tr.t("charts.unit_m3"), ViewUnit.KWH: self._tr.t("charts.unit_kwh")}
        self._year_from_label.setText(self._tr.t("charts.year_from"))
        self._year_to_label.setText(self._tr.t("charts.year_to"))
        self._empty_label.setText(self._tr.t("charts.empty"))
        self._trend.setText(self._tr.t("charts.trend"))
        self._proj_prev.setText(self._tr.t("charts.projection_prev"))
        self._repopulate_preset_combo()
        self._repopulate_combo(self._agg, self._aggregations)
        self._repopulate_combo(self._unit, self._units)
        for card in (self._meter_card, self._usage_card, self._monthly_card):
            if card is not None:
                card.retranslate()
        self._render()

    @staticmethod
    def _repopulate_combo(combo: QComboBox, data_map: dict) -> None:
        """Replace a combo's items, preserving the current selection."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for key, label in data_map.items():
            combo.addItem(label, key)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        combo.blockSignals(False)

    def _repopulate_preset_combo(self) -> None:
        current = self._preset.currentData()
        self._preset.blockSignals(True)
        self._preset.clear()
        self._preset.addItem(self._tr.t("table.filter_custom"), None)
        for key, label in (
            ("all", "table.filter_all"),
            ("this_year", "charts.preset_this_year"),
            ("last_year", "charts.preset_last_year"),
            ("last3", "charts.preset_last3"),
        ):
            self._preset.addItem(self._tr.t(label), key)
        index = self._preset.findData(current)
        self._preset.setCurrentIndex(index if index >= 0 else 0)
        self._preset.blockSignals(False)

    # -- event handlers --------------------------------------------------------------
    def _controller_or_none(self):
        return self._controller

    def _on_preset(self) -> None:
        controller = self._controller_or_none()
        preset = self._preset.currentData()
        if preset is None:
            self._apply_year_range()
            return
        if controller is not None:
            controller.apply_charts_preset(preset)

    def _on_year_changed(self) -> None:
        self._preset.blockSignals(True)
        self._preset.setCurrentIndex(self._preset.findData(None))
        self._preset.blockSignals(False)
        self._apply_year_range()

    def _apply_year_range(self) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_charts_years(self._year_from.value(), self._year_to.value())

    def _on_unit(self) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_unit(self._unit.currentData())

    def _on_agg(self) -> None:
        """Aggregation is part of the shared controller state (AJAX)."""
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_aggregation(self._agg.currentData())
        else:
            # standalone usage (tests / no controller): local render only
            self._render()

    def _on_trend(self, checked: bool) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_trendline(checked)
        else:
            self._render()

    def _on_proj_prev(self, checked: bool) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_project_by_previous_year(checked)
        else:
            self._render()

    # -- rendering --------------------------------------------------------------------
    def _render(self) -> None:
        dashboard = self._dashboard
        has_data = dashboard is not None and bool(dashboard.meter_series)
        self._empty_label.setVisible(not has_data)
        if dashboard is None:
            return
        self._sync_widgets()
        for card in (self._kpi_card, self._meter_card, self._usage_card, self._monthly_card):
            if card is not None:
                card.setVisible(has_data)
        self._render_kpis(dashboard)
        self._render_meter(dashboard)
        self._render_usage(dashboard)
        self._render_monthly(dashboard)

    def _sync_widgets(self) -> None:
        if self._kpi_card is None:
            self._kpi_card = KpiCard(self._tr, self._dark)
            self._cards.addWidget(self._kpi_card, 1, 0, 1, 2)
        if self._meter_card is None:
            self._meter_card = ChartCard(self._tr.t("charts.meter.title"), self._tr, self._dark)
            self._cards.addWidget(self._meter_card, 2, 0)
            self._meter_view = self._meter_card.view
        if self._usage_card is None:
            self._usage_card = ChartCard(self._tr.t("charts.usage.title"), self._tr, self._dark)
            self._cards.addWidget(self._usage_card, 2, 1)
            self._usage_view = self._usage_card.view
        if self._monthly_card is None:
            self._monthly_card = ChartCard(self._tr.t("charts.monthly.title"), self._tr, self._dark)
            self._cards.addWidget(self._monthly_card, 3, 0, 1, 2)
            self._monthly_view = self._monthly_card.view

    def _render_kpis(self, dashboard: Dashboard) -> None:
        self._kpi_card.render(dashboard)

    def _render_meter(self, dashboard: Dashboard) -> None:
        daily = dashboard.consumption.get(Aggregation.DAILY, [])
        builder = _meter_chart_builder(dashboard.meter_series, daily, self._dark, self._tr)
        unit = dashboard.unit.value
        self._meter_card.set_chart(builder, title=f"{self._tr.t('charts.meter.title')} ({unit})")

    def _render_usage(self, dashboard: Dashboard) -> None:
        agg = self._agg.currentData()
        trend_on = self._trend.isChecked()
        agg_label = self._aggregations[agg]
        builder = _usage_chart_builder(dashboard, agg, trend_on, self._dark, self._tr)
        unit = dashboard.unit.value
        self._usage_card.set_chart(
            builder,
            title=f"{self._tr.t('charts.usage.title')} — {agg_label} ({unit})",
        )

    def _render_monthly(self, dashboard: Dashboard) -> None:
        builder = _monthly_chart_builder(dashboard, self._dark, self._tr)
        unit = dashboard.unit.value
        self._monthly_card.set_chart(builder, title=f"{self._tr.t('charts.monthly.title')} ({unit})")
