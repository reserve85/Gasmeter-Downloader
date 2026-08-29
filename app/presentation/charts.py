"""Charts tab - scrollable dashboard of KPI, meter, usage and monthly cards.

Driven entirely by a single `Dashboard`; switching unit/aggregation only picks
precomputed series (instant). Charts re-theme on ``apply_theme``.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QDateTimeAxis,
    QLineSeries,
    QValueAxis,
)
from PyQt6.QtCore import QDate, QDateTime, QTime, Qt
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.aggregation import shift_previous
from app.domain.entities import Aggregation, Dashboard, ViewUnit
from app.domain.conversion import point_value
from app.presentation.i18n import Translator

_EPOCH = date(1970, 1, 1)


def _days_since_epoch(day: date) -> float:
    return float((day - _EPOCH).days)


def _to_qdatetime(day: date) -> QDateTime:
    return QDateTime(QDate(day.year, day.month, day.day), QTime(0, 0, 0))


def _make_chart(dark: bool) -> QChart:
    chart = QChart()
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    chart.setTheme(QChart.ChartTheme.ChartThemeDark if dark else QChart.ChartTheme.ChartThemeLight)
    return chart
def _build_card(title: str, body: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.addWidget(body)
    return box


def _bar_chart(categories: list[str], sets: list[tuple[str, list[float]]], dark: bool) -> QChart:
    chart = _make_chart(dark)
    bar_series = QBarSeries()
    for label, values in sets:
        bar_set = QBarSet(label)
        for value in values:
            bar_set.append(value)
        bar_series.append(bar_set)
    chart.addSeries(bar_series)
    axis_x = QBarCategoryAxis()
    axis_x.append(categories)
    axis_y = QValueAxis()
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    bar_series.attachAxis(axis_x)
    bar_series.attachAxis(axis_y)
    return chart


def _line_chart(points: list[tuple[float, float]], dark: bool) -> QChart:
    chart = _make_chart(dark)
    line = QLineSeries()
    for x, y in points:
        line.append(x, y)
    chart.addSeries(line)
    axis_x = QDateTimeAxis()
    axis_x.setFormat("yyyy-MM")
    axis_y = QValueAxis()
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    line.attachAxis(axis_x)
    line.attachAxis(axis_y)
    if points:
        xs = [p[0] for p in points]
        axis_x.setRange(_qdt(xs[0]), _qdt(xs[-1]))
    return chart


def _qdt(days_since_epoch: float) -> QDateTime:
    from datetime import timedelta

    d = _EPOCH + timedelta(days=days_since_epoch)
    return QDateTime(QDate(d.year, d.month, d.day), QTime(0, 0, 0))
class ChartsTab(QWidget):
    """Scrollable card dashboard bound to a DashboardController."""

    def __init__(self, tr: Translator, dark: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._tr = tr
        self._dark = dark
        self._dashboard: Dashboard | None = None
        self._aggs = {
            Aggregation.DAILY: tr.t("charts.agg.daily"),
            Aggregation.WEEKLY: tr.t("charts.agg.weekly"),
            Aggregation.MONTHLY: tr.t("charts.agg.monthly"),
        }
        self._units = {ViewUnit.M3: tr.t("charts.unit_m3"), ViewUnit.KWH: tr.t("charts.unit_kwh")}

        root = QVBoxLayout(self)
        root.addLayout(self._build_controls())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._cards = QVBoxLayout(content)
        self._empty_label = QLabel(tr.t("charts.empty"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cards.addWidget(self._empty_label)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._meter_view: QChartView | None = None
        self._usage_view: QChartView | None = None
        self._monthly_view: QChartView | None = None
        self._kpi_widget: QWidget | None = None

    # -- controls ---------------------------------------------------------------
    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._from_edit = QDateEdit(QDate.currentDate().addMonths(-1))
        self._to_edit = QDateEdit(QDate.currentDate())
        for edit in (self._from_edit, self._to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self._preset = QComboBox()
        for key in ("all", "30d", "90d", "year"):
            self._preset.addItem(self._tr.t(f"table.filter_{key}") if key != "all" else self._tr.t("table.filter_all"), key)
        self._agg = QComboBox()
        for agg, label in self._aggs.items():
            self._agg.addItem(label, agg)
        self._unit = QComboBox()
        for unit, label in self._units.items():
            self._unit.addItem(label, unit)
        self._yoy = QCheckBox(self._tr.t("charts.yoy"))
        self._trend = QCheckBox(self._tr.t("charts.trend"))

        row.addWidget(QLabel(self._tr.t("charts.from")))
        row.addWidget(self._from_edit)
        row.addWidget(QLabel(self._tr.t("charts.to")))
        row.addWidget(self._to_edit)
        row.addWidget(self._preset)
        row.addWidget(self._agg)
        row.addWidget(self._unit)
        row.addWidget(self._yoy)
        row.addWidget(self._trend)
        row.addStretch(1)

        self._preset.currentIndexChanged.connect(self._on_preset)
        self._from_edit.dateChanged.connect(self._on_range)
        self._to_edit.dateChanged.connect(self._on_range)
        self._agg.currentIndexChanged.connect(self._render)
        self._unit.currentIndexChanged.connect(self._on_unit)
        self._yoy.toggled.connect(self._on_yoy)
        self._trend.toggled.connect(self._on_trend)
        return row

    # -- controller wiring ------------------------------------------------------
    def bind(self, controller) -> None:
        self._controller = controller
        controller.dashboard_changed.connect(self.set_dashboard)

    def set_dashboard(self, dashboard: Dashboard) -> None:
        self._dashboard = dashboard
        unit = dashboard.unit
        index = self._unit.findData(unit)
        if index >= 0 and index != self._unit.currentIndex():
            self._unit.blockSignals(True)
            self._unit.setCurrentIndex(index)
            self._unit.blockSignals(False)
        self._render()

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._render()

    # -- event handlers ----------------------------------------------------------
    def _controller_or_none(self):
        return getattr(self, "_controller", None)

    def _on_preset(self) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.apply_preset(self._preset.currentData())

    def _on_range(self) -> None:
        controller = self._controller_or_none()
        if controller is None:
            return
        from datetime import date as dt_date

        start = self._from_edit.date()
        end = self._to_edit.date()
        controller.set_date_range(
            dt_date(start.year(), start.month(), start.day()),
            dt_date(end.year(), end.month(), end.day()),
        )

    def _on_unit(self) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_unit(self._unit.currentData())

    def _on_yoy(self, checked: bool) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_include_previous_year(checked)

    def _on_trend(self, checked: bool) -> None:
        controller = self._controller_or_none()
        if controller is not None:
            controller.set_trendline(checked)
# -- rendering --------------------------------------------------------------
    def _render(self) -> None:
        dashboard = self._dashboard
        self._empty_label.setVisible(dashboard is None or not dashboard.meter_series)
        if dashboard is None:
            return
        self._sync_widgets(dashboard)
        self._render_kpis(dashboard)
        self._render_meter(dashboard)
        self._render_usage(dashboard)
        self._render_monthly(dashboard)

    def _sync_widgets(self, dashboard: Dashboard) -> None:

        if self._meter_view is None:
            self._meter_view = QChartView()
            self._cards.addWidget(_build_card(self._tr.t("charts.meter.title"), self._meter_view))
        if self._usage_view is None:
            self._usage_view = QChartView()
            self._cards.addWidget(_build_card(self._tr.t("charts.usage.title"), self._usage_view))
        if self._monthly_view is None:
            self._monthly_view = QChartView()
            self._cards.addWidget(_build_card(self._tr.t("charts.monthly.title"), self._monthly_view))

    def _render_kpis(self, dashboard: Dashboard) -> None:
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout

        kpi = dashboard.kpi
        max_day_text = (
            self._tr.format_date(kpi.max_day.day) + " · " + self._tr.format_number(point_value(kpi.max_day, dashboard.unit))
            if kpi.max_day
            else "–"
        )
        box = QGroupBox("Overview")
        grid = QGridLayout(box)
        labels = [
            (self._tr.t("charts.kpi.total"), self._tr.format_number(kpi.total_energy)),
            (self._tr.t("charts.kpi.avg_day"), self._tr.format_number(kpi.average_per_day)),
            (self._tr.t("charts.kpi.max_day"), max_day_text),
            (self._tr.t("charts.kpi.interpolated"), str(kpi.interpolated_days_in_range)),
            (self._tr.t("charts.kpi.latest"), self._tr.format_number(kpi.latest_meter_value)),
        ]
        for i, (title, value) in enumerate(labels):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: bold;")
            cell_layout.addWidget(title_label)
            cell_layout.addWidget(QLabel(value))
            grid.addWidget(cell, 0, i)
        if self._kpi_widget is not None:
            self._cards.removeWidget(self._kpi_widget)
            self._kpi_widget.deleteLater()
        self._kpi_widget = box
        self._cards.insertWidget(0, box)

    def _render_meter(self, dashboard: Dashboard) -> None:
        points = [(_days_since_epoch(p.day), float(p.display_value)) for p in dashboard.meter_series]
        chart = _line_chart(points, self._dark)
        chart.setTitle(f"{self._tr.t('charts.meter.title')} ({dashboard.unit.value})")
        self._meter_view.setChart(chart)
    def _render_usage(self, dashboard: Dashboard) -> None:
        agg = self._agg.currentData()
        unit = self._unit.currentData()
        current = dashboard.consumption.get(agg, [])
        prev_map = {p.day: p for p in (dashboard.previous_year or {}).get(agg, [])}
        sets = [(dashboard.unit.value, [float(point_value(p, unit)) for p in current])]
        if self._yoy.isChecked():
            prev_values = []
            for p in current:
                target = shift_previous(p.day, agg)
                prev_values.append(float(point_value(prev_map[target], unit)) if target in prev_map else 0.0)
            sets.append((self._tr.t("charts.yoy"), prev_values))
        categories = [self._tr.format_date(p.day) for p in current]
        if self._trend.isChecked() and dashboard.trendline is not None and agg == Aggregation.DAILY:
            cats = set(categories)
            for p in dashboard.trendline.series.points:
                label = self._tr.format_date(p.day)
                if label not in cats:
                    categories.append(label)
                    cats.add(label)
        chart = _bar_chart(categories, sets, self._dark)
        if self._trend.isChecked() and dashboard.trendline is not None and agg == Aggregation.DAILY:
            order = {label: i for i, label in enumerate(categories)}
            overlay_points: dict[int, float] = {}
            for p in dashboard.trendline.series.points:
                idx = order.get(self._tr.format_date(p.day))
                if idx is not None:
                    overlay_points[idx] = float(point_value(p, unit))
            overlay = QLineSeries()
            for idx in sorted(overlay_points):
                overlay.append(float(idx), overlay_points[idx])
            overlay.setPen(QPen(Qt.GlobalColor.darkRed, 2, Qt.PenStyle.DashLine))
            chart.addSeries(overlay)
            overlay.attachAxis(chart.axes(Qt.Orientation.Horizontal)[0])
            overlay.attachAxis(chart.axes(Qt.Orientation.Vertical)[0])
        chart.setTitle(f"{self._tr.t('charts.usage.title')} — {self._aggs[agg]}")
        self._usage_view.setChart(chart)

    def _render_monthly(self, dashboard: Dashboard) -> None:
        unit = self._unit.currentData()
        monthly = dashboard.consumption.get(Aggregation.MONTHLY, [])
        prev_map = {p.day: p for p in (dashboard.previous_year or {}).get(Aggregation.MONTHLY, [])}
        sets = [(dashboard.unit.value, [float(point_value(p, unit)) for p in monthly])]
        if self._yoy.isChecked():
            prev_values = []
            for p in monthly:
                target = shift_previous(p.day, Aggregation.MONTHLY)
                prev_values.append(float(point_value(prev_map[target], unit)) if target in prev_map else 0.0)
            sets.append((self._tr.t("charts.yoy"), prev_values))
        categories = [self._tr.format_date(p.day) for p in monthly]
        chart = _bar_chart(categories, sets, self._dark)
        chart.setTitle(self._tr.t("charts.monthly.title"))
        self._monthly_view.setChart(chart)
