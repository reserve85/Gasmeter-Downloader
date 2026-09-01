"""Compare tab - two years side by side across all three chart types.

Mirrors the main charts page (meter, usage, monthly) but always renders two
value pairs: year A and year B. Lines are overlaid, monthly bars sit side by
side, and every point/bar carries its own hover/click info bubble with the
correct year-specific values. All charts are Matplotlib ``MplRender`` figures
(``mpl_charts``); the yearly from/to pickers of the charts tab do not apply
here; the unit is shared with the rest of the app via the dashboard controller.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from matplotlib import dates as mdates
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.application.models import QueryRequest
from app.domain.conversion import point_value
from app.domain.entities import Aggregation, ViewUnit
from app.presentation.charts import BigChartDialog
from app.presentation.i18n import Translator
from app.presentation.mpl_charts import (
    MplRender,
    _HoverTarget,
    _COMPARE_COLORS,
    _SERIES_COLOR,
    _TEXT_COLOR,
    _bar_tolerances,
    _bar_value_labels,
    _date2num,
    _line_tolerances,
    _make_canvas,
    _style_axes,
    _tooltip_text,
)

_MONTH_COUNT = 12
_CHART_MIN_HEIGHT = 200

#: compare monthly bars: the LOWER year is blue on the LEFT, the HIGHER year
#: green on the RIGHT (same green as the charts-tab balkendiagramm)
_COMPARE_BAR_BLUE = _COMPARE_COLORS[1]  # same blue as the compare line charts


def _compare_year_colors(year_a: int, year_b: int) -> tuple[str, str]:
    """``(color_a, color_b)``: the HIGHER year is green, the LOWER year blue.

    Used by ALL compare charts (bars + meter + usage lines) so the years keep
    the same color everywhere, regardless of which slot (A/B) they sit in.
    """
    if year_a > year_b:
        return _SERIES_COLOR, _COMPARE_BAR_BLUE
    return _COMPARE_BAR_BLUE, _SERIES_COLOR


class CompareTab(QWidget):
    """Year-over-year comparison: all three main charts with two series each."""

    def __init__(self, query_use_case, settings, logger, tr: Translator, dark: bool = False, parent=None):
        super().__init__(parent)
        self._use_case = query_use_case
        self._settings = settings
        self._logger = logger
        self._tr = tr
        self._dark = dark
        self._agg = Aggregation.DAILY
        raw_unit = settings.get("app.unit", "m³")
        self._unit = ViewUnit.M3 if raw_unit == "m³" else ViewUnit.KWH

        self._last_renders: dict[str, MplRender] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._build_controls())
        root.addLayout(self._build_kpi_row())
        root.addWidget(self._build_chart_area(), 1)

        now = date.today()
        self._year_a.setValue(now.year - 1)
        self._year_b.setValue(now.year)
        self._recompute()


# -- construction -----------------------------------------------------------
    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._year_a_label = QLabel(self._tr.t("compare.year_a"))
        self._year_a = QSpinBox()
        self._year_a.setRange(1990, 2100)
        self._year_b_label = QLabel(self._tr.t("compare.year_b"))
        self._year_b = QSpinBox()
        self._year_b.setRange(1990, 2100)

        self._aggregations = {
            Aggregation.DAILY: self._tr.t("charts.agg.daily"),
            Aggregation.WEEKLY: self._tr.t("charts.agg.weekly"),
            Aggregation.MONTHLY: self._tr.t("charts.agg.monthly"),
        }
        self._agg_combo = QComboBox()
        for agg, label in self._aggregations.items():
            self._agg_combo.addItem(label, agg)

        self._units = {
            ViewUnit.M3: self._tr.t("charts.unit_m3"),
            ViewUnit.KWH: self._tr.t("charts.unit_kwh"),
        }
        self._unit_combo = QComboBox()
        for unit, label in self._units.items():
            self._unit_combo.addItem(label, unit)
        self._unit_combo.setCurrentIndex(self._unit_combo.findData(self._unit))

        self._hint = QLabel(self._tr.t("compare.hint"))
        self._hint.setStyleSheet("color: gray;")

        row.addWidget(self._year_a_label)
        row.addWidget(self._year_a)
        row.addWidget(self._year_b_label)
        row.addWidget(self._year_b)
        row.addWidget(self._agg_combo)
        row.addWidget(self._unit_combo)
        row.addWidget(self._hint)
        row.addStretch(1)

        self._year_a.valueChanged.connect(self._recompute)
        self._year_b.valueChanged.connect(self._recompute)
        self._agg_combo.currentIndexChanged.connect(self._on_agg)
        self._unit_combo.currentIndexChanged.connect(self._on_unit)
        return row

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._total_a_label = QLabel("")
        self._total_b_label = QLabel("")
        self._delta_label = QLabel("")
        for label in (self._total_a_label, self._total_b_label, self._delta_label):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(label)
        row.addStretch(1)
        return row


    def _build_chart_area(self) -> QWidget:
        area = QWidget(self)
        grid = QGridLayout(area)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self._meter_view = self._new_view(area)
        self._usage_view = self._new_view(area)
        self._monthly_view = self._new_view(area)
        grid.addWidget(self._meter_view, 0, 0)
        grid.addWidget(self._usage_view, 0, 1)
        grid.addWidget(self._monthly_view, 1, 0, 1, 2)
        # every chart click is logged so the owner can verify "where is my mouse"
        from app.domain.entities import LogCategory, LogLevel

        for view in (self._meter_view, self._usage_view, self._monthly_view):
            view.set_click_logger(
                lambda line: self._logger.log(LogCategory.GUI, LogLevel.INFO, line)
            )
        self._meter_view.set_double_click_callback(lambda: self._open_big("meter"))
        self._usage_view.set_double_click_callback(lambda: self._open_big("usage"))
        self._monthly_view.set_double_click_callback(lambda: self._open_big("monthly"))
        self._empty_label = QLabel(self._tr.t("charts.empty"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        grid.addWidget(self._empty_label, 0, 0, 2, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        return area

    @staticmethod
    def _new_view(parent: QWidget):
        return _make_canvas(parent, min_height=_CHART_MIN_HEIGHT)

    # -- public API -------------------------------------------------------------
    def bind(self, controller) -> None:
        """Share the selected unit with the charts tab (AJAX)."""
        controller.charts_dashboard_changed.connect(self._on_controller_dashboard)

    def _on_controller_dashboard(self, dashboard) -> None:
        if dashboard.unit != self._unit:
            self._unit = dashboard.unit
            self._unit_combo.blockSignals(True)
            index = self._unit_combo.findData(dashboard.unit)
            self._unit_combo.setCurrentIndex(index if index >= 0 else 0)
            self._unit_combo.blockSignals(False)
        self._recompute()

    def _on_agg(self) -> None:
        self._agg = self._agg_combo.currentData()
        self._recompute()

    def _on_unit(self) -> None:
        self._unit = self._unit_combo.currentData()
        self._recompute()

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self._recompute()

    def retranslate(self) -> None:
        self._year_a_label.setText(self._tr.t("compare.year_a"))
        self._year_b_label.setText(self._tr.t("compare.year_b"))
        self._hint.setText(self._tr.t("compare.hint"))
        self._empty_label.setText(self._tr.t("charts.empty"))
        self._repopulate_combo(self._agg_combo, self._aggregations)
        self._repopulate_combo(self._unit_combo, self._units)
        self._recompute()

    @staticmethod
    def _repopulate_combo(combo: QComboBox, data_map: dict) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for key, label in data_map.items():
            combo.addItem(label, key)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        combo.blockSignals(False)

    # -- data / rendering ---------------------------------------------------------
    def _open_big(self, key: str) -> None:
        """Open the selected compare chart in a resizable big dialog."""
        render = self._last_renders.get(key)
        if render is None:
            return
        title_map = {
            "meter": self._tr.t("charts.meter.title"),
            "usage": self._tr.t("charts.usage.title"),
            "monthly": self._tr.t("charts.monthly.title"),
        }
        title = self._tr.t("charts.big.title", title=title_map.get(key, key))
        BigChartDialog(render, title, self._dark, self).exec()

    def _query(self, year: int) -> object:
        return self._use_case.run(
            QueryRequest(
                start=date(year, 1, 1),
                end=date(year, 12, 31),
                unit=self._unit,
                aggregation=self._agg,
                include_previous_year=False,
                with_trendline=False,
                with_year_projection=False,
            )
        )

    def _recompute(self) -> None:
        year_a = self._year_a.value()
        year_b = self._year_b.value()
        dash_a = self._query(year_a)
        dash_b = self._query(year_b)

        total_a = dash_a.kpi.total_energy if dash_a.table_rows else Decimal("0")
        total_b = dash_b.kpi.total_energy if dash_b.table_rows else Decimal("0")
        delta = total_a - total_b
        unit = self._unit.value
        self._total_a_label.setText(
            f"{self._tr.t('compare.usage')} {year_a}: {self._tr.format_number(total_a)} {unit}"
        )
        self._total_b_label.setText(
            f"{self._tr.t('compare.usage')} {year_b}: {self._tr.format_number(total_b)} {unit}"
        )
        self._delta_label.setText(
            f"{self._tr.t('compare.delta')}: {self._tr.format_number(delta)} {unit}"
        )

        has_data = bool(dash_a.meter_series) or bool(dash_b.meter_series)
        for view in (self._meter_view, self._usage_view, self._monthly_view):
            view.setVisible(has_data)
        self._empty_label.setVisible(not has_data)
        if not has_data:
            return

        meter_render = _compare_meter_render(dash_a, dash_b, year_a, year_b, self._dark, self._tr)()
        usage_render = _compare_usage_render(dash_a, dash_b, year_a, year_b, self._agg, self._dark, self._tr)()
        monthly_render = _compare_monthly_render(dash_a, dash_b, year_a, year_b, self._dark, self._tr)()
        self._last_renders = {
            "meter": meter_render,
            "usage": usage_render,
            "monthly": monthly_render,
        }
        self._meter_view.store_interaction(meter_render)
        self._usage_view.store_interaction(usage_render)
        self._monthly_view.store_interaction(monthly_render)


# -- two-year chart builders ---------------------------------------------------------
# Both years are drawn on a SHARED Jan-Dec x axis (overlay, not sequential) so
# they can be compared per season. The reference year only carries the month/day
# layout; the tooltip texts always show the real dates.
_OVERLAY_YEAR = 2000  # leap year -> Feb 29 from the source data maps 1:1


def _overlay_num(day: date) -> float:
    return _date2num(date(_OVERLAY_YEAR, day.month, day.day))


def _overlay_axes(ax, dark: bool) -> None:
    """Shared Jan 1 - Dec 31 date axis so both years compare over the same season."""
    _style_axes(ax, dark)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.set_xlim(_date2num(date(_OVERLAY_YEAR, 1, 1)), _date2num(date(_OVERLAY_YEAR, 12, 31)))


def _year_to_date_suffix(dash, day: date, tr: Translator) -> str:
    """Extra hover line: consumption from Jan 1 up to ``day`` of that year."""
    daily = dash.consumption.get(Aggregation.DAILY, [])
    total_m3 = sum((p.volume_m3 for p in daily if p.day <= day), Decimal("0"))
    total_kwh = sum((p.energy_kwh for p in daily if p.day <= day), Decimal("0"))
    return (
        f"\n{tr.t('charts.tt.year_to_date')}: "
        f"{tr.format_number(total_m3)} m³ / {tr.format_number(total_kwh)} kWh"
    )


def _compare_meter_render(dash_a, dash_b, year_a: int, year_b: int, dark: bool, tr: Translator):
    """Two overlaid meter lines that each start at 0 on Jan 1 (per-year usage).

    The absolute meter readout differs by year by tens of thousands; to make
    the curves comparable the series are normalized to the year's first value.
    The tooltip still shows the absolute meter value of that day.
    """

    def build() -> MplRender:
        targets: list[_HoverTarget] = []
        all_xs: list[float] = []
        all_ys: list[float] = []
        series_data: list[tuple[list[float], list[float], str, str]] = []
        color_a, color_b = _compare_year_colors(year_a, year_b)
        for dash, label, color in (
            (dash_a, str(year_a), color_a),
            (dash_b, str(year_b), color_b),
        ):
            points = dash.meter_series
            if not points:
                continue
            base = float(points[0].display_value)
            daily_by_day = {c.day: c for c in dash.consumption.get(Aggregation.DAILY, [])}
            line_xs: list[float] = []
            line_ys: list[float] = []
            for point in points:
                x = _overlay_num(point.day)
                y = float(point.display_value) - base
                line_xs.append(x)
                line_ys.append(y)
                delta = daily_by_day.get(point.day)
                targets.append(
                    _HoverTarget(
                        x,
                        y,
                        _tooltip_text(
                            point.day,
                            point.adjusted_value,
                            delta.volume_m3 if delta else Decimal("0"),
                            delta.energy_kwh if delta else Decimal("0"),
                            tr,
                        )
                        + _year_to_date_suffix(dash, point.day, tr),
                    )
                )
                all_xs.append(x)
                all_ys.append(y)
            series_data.append((line_xs, line_ys, f"{label} · {tr.t('charts.meter.title')}", color))
        x_tol, y_tol = _line_tolerances(all_xs, all_ys)

        def draw(ax) -> None:
            _overlay_axes(ax, dark)
            for line_xs, line_ys, label, color in series_data:
                ax.plot(
                    line_xs,
                    line_ys,
                    color=color,
                    marker="o",
                    markersize=3,
                    linewidth=1.5,
                    label=label,
                )
            if series_data:
                ax.legend(loc="best", fontsize=8, frameon=False, labelcolor=_TEXT_COLOR[dark])

        return MplRender(draw=draw, targets=targets, x_tol=x_tol, y_tol=y_tol)

    return build


def _compare_usage_render(dash_a, dash_b, year_a: int, year_b: int, agg: Aggregation, dark: bool, tr: Translator):
    """Two overlaid usage lines (one per year) on the shared Jan-Dec axis."""

    def build() -> MplRender:
        targets: list[_HoverTarget] = []
        all_xs: list[float] = []
        all_ys: list[float] = []
        series_data: list[tuple[list[float], list[float], str, str]] = []
        unit = dash_a.unit
        color_a, color_b = _compare_year_colors(year_a, year_b)
        for dash, label, color in (
            (dash_a, str(year_a), color_a),
            (dash_b, str(year_b), color_b),
        ):
            points = dash.consumption.get(agg, [])
            if not points:
                continue
            meter_by_day = {m.day: m for m in dash.meter_series}
            line_xs: list[float] = []
            line_ys: list[float] = []
            for point in points:
                x = _overlay_num(point.day)
                y = float(point_value(point, unit))
                line_xs.append(x)
                line_ys.append(y)
                meter = meter_by_day.get(point.day)
                targets.append(
                    _HoverTarget(
                        x,
                        y,
                        _tooltip_text(
                            point.day,
                            meter.adjusted_value if meter else Decimal("0"),
                            point.volume_m3,
                            point.energy_kwh,
                            tr,
                        )
                        + _year_to_date_suffix(dash, point.day, tr),
                    )
                )
                all_xs.append(x)
                all_ys.append(y)
            series_data.append((line_xs, line_ys, f"{label} · {tr.t('charts.usage.title')}", color))
        x_tol, y_tol = _line_tolerances(all_xs, all_ys)

        def draw(ax) -> None:
            _overlay_axes(ax, dark)
            for line_xs, line_ys, label, color in series_data:
                ax.plot(
                    line_xs,
                    line_ys,
                    color=color,
                    marker="o",
                    markersize=3,
                    linewidth=1.5,
                    label=label,
                )
            if series_data:
                ax.legend(loc="best", fontsize=8, frameon=False, labelcolor=_TEXT_COLOR[dark])

        return MplRender(draw=draw, targets=targets, x_tol=x_tol, y_tol=y_tol)

    return build


def _compare_monthly_render(dash_a, dash_b, year_a: int, year_b: int, dark: bool, tr: Translator):
    """Two side-by-side bar sets (one per year) with per-bar month/year info.

    The LOWER year sits on the LEFT half of each category and is blue; the
    HIGHER year sits on the RIGHT half and is green (same green as the
    charts-tab monthly bars). Each bar gets its own snap target at the *center
    of that bar*, so hovering over one year's half always shows that year's
    month.
    """
    unit = dash_a.unit
    values_a, points_a = _monthly_values(dash_a, unit)
    values_b, points_b = _monthly_values(dash_b, unit)
    # lower year -> LEFT (-0.21) blue, higher year -> RIGHT (+0.21) green
    color_a, color_b = _compare_year_colors(year_a, year_b)
    if year_a > year_b:
        offset_a, offset_b = 0.21, -0.21
    else:
        offset_a, offset_b = -0.21, 0.21

    def build() -> MplRender:
        targets: list[_HoverTarget] = []
        year_offsets = {year_a: offset_a, year_b: offset_b}
        for year, values, points in (
            (year_a, values_a, points_a),
            (year_b, values_b, points_b),
        ):
            offset = year_offsets[year]
            for month in range(1, _MONTH_COUNT + 1):
                value = values[month - 1]
                if value <= 0:
                    continue
                x = float(month - 1) + offset
                targets.append(_HoverTarget(x, value, _bar_tooltip(year, month, points[month - 1], tr)))

        def draw(ax) -> None:
            _style_axes(ax, dark)
            xs = [m - 1 for m in range(1, _MONTH_COUNT + 1)]
            bars_a = ax.bar(
                [x + offset_a for x in xs],
                values_a,
                width=0.4,
                color=color_a,
                edgecolor="none",
                label=str(year_a),
            )
            bars_b = ax.bar(
                [x + offset_b for x in xs],
                values_b,
                width=0.4,
                color=color_b,
                edgecolor="none",
                label=str(year_b),
            )
            ax.set_xticks(xs)
            ax.set_xticklabels([f"{m:02d}" for m in range(1, _MONTH_COUNT + 1)], fontsize=8)
            ax.set_xlim(-0.5, _MONTH_COUNT - 0.5)
            ax.margins(y=0.15)
            _bar_value_labels(ax, bars_a, unit.value, dark, tr)
            _bar_value_labels(ax, bars_b, unit.value, dark, tr)
            ax.legend(loc="best", fontsize=8, frameon=False, labelcolor=_TEXT_COLOR[dark])

        return MplRender(
            draw=draw,
            targets=targets,
            x_tol=0.21,
            y_tol=_bar_tolerances(values_a + values_b) or 1.0,
            bar_hit=True,
        )

    return build


def _monthly_values(dashboard, unit: ViewUnit) -> tuple[list[float], list]:
    """(values per month 1..12, points per month) - missing months become 0."""
    by_month = {point.day.month: point for point in dashboard.consumption.get(Aggregation.MONTHLY, [])}
    values = [
        float(point_value(by_month[m], unit)) if m in by_month else 0.0
        for m in range(1, _MONTH_COUNT + 1)
    ]
    points = [by_month.get(m) for m in range(1, _MONTH_COUNT + 1)]
    return values, points


def _bar_tooltip(year: int, month: int, point, tr: Translator) -> str:
    """Per-bar info text: Monat/Jahr + monthly usage of THAT bar's year."""
    if point is None:
        return f"{month:02d}/{year}\n{tr.t('charts.tt.usage_month')}: 0 m³\n0 kWh"
    return _tooltip_text(date(year, month, 1), Decimal("0"), point.volume_m3, point.energy_kwh, tr, monthly=True)
