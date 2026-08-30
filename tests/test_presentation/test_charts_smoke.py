"""ChartsTab / CompareTab tests (offscreen) for the Matplotlib chart stack.

The diagrams (and their labels/hover/click behaviour) are Matplotlib
``MplRender`` figures on ``MplChartCanvas``; hover/click events are driven
through the canvas's own Matplotlib callback pipeline with data-space
coordinates (deterministic offscreen, no widget-pixel round-trip needed).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from unittest import mock

from matplotlib.backend_bases import MouseEvent
from matplotlib.lines import Line2D
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDateEdit, QSpinBox

from app.application.models import QueryRequest
from app.application.use_cases.query import GetDashboardUseCase
from app.domain.entities import Aggregation, ViewUnit
from app.presentation.charts import (
    BigChartDialog,
    ChartsTab,
    _meter_chart_builder,
    _monthly_chart_builder,
    _usage_chart_builder,
)
from app.presentation.i18n import Translator
from app.presentation.mpl_charts import (
    MplChartCanvas,
    MplRender,
    _HoverTarget,
    _bar_target_at,
    _date2num,
    _nearest_target,
    _style_axes,
    _tooltip_text,
)

from tests.conftest import FakeSettings, FixedClock, RecordingLogger


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


def _compare_tab(fake_repo, gas_repo, tr=None):
    from app.presentation.compare import CompareTab

    return CompareTab(
        GetDashboardUseCase(
            fake_repo, gas_repo, FakeSettings({"app.unit": "m³"}), RecordingLogger()
        ),
        FakeSettings({"app.unit": "m³"}),
        RecordingLogger(),
        tr or Translator("en"),
    )


def _drive(canvas, name, xd, yd, button=None):
    """Push a Matplotlib event through the canvas's own pipeline (data coords)."""
    dx, dy = canvas.axes.transData.transform((xd, yd))
    event = MouseEvent(name, canvas, dx, dy, button=button)
    canvas.callbacks.process(name, event)


# -- ChartsTab: build / controls / theme -------------------------------------
def test_charts_tab_builds_and_renders(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    assert tab._meter_view is not None  # noqa: SLF001
    assert tab._usage_view is not None  # noqa: SLF001
    assert tab._monthly_view is not None  # noqa: SLF001
    assert len(tab._meter_view.axes.lines) >= 1


def test_charts_tab_switch_aggregation_unit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)

    tab._agg.setCurrentIndex(2)  # monthly  # noqa: SLF001
    tab._render()  # noqa: SLF001
    tab._unit.setCurrentIndex(1)  # kWh  # noqa: SLF001
    tab._render()  # noqa: SLF001
    # no exceptions raised


def test_charts_tab_toggles_trend_and_projection(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)

    tab._trend.setChecked(True)  # noqa: SLF001
    tab._proj_prev.setChecked(True)  # noqa: SLF001
    tab._render()  # noqa: SLF001
    assert dashboard.trendline is not None


def test_charts_tab_theme_change(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    tab.apply_theme(True)  # dark
    assert tab._dark is True  # noqa: SLF001


def test_charts_tab_empty_state(qapp, fake_repo, gas_repo):
    logger = RecordingLogger()
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(_dashboard(fake_repo, gas_repo, logger))  # empty dataset renders fine
    assert tab._empty_label is not None  # noqa: SLF001


def test_charts_year_selector_is_spinbox_not_dateedit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    assert isinstance(tab._year_from, QSpinBox)  # noqa: SLF001
    assert isinstance(tab._year_to, QSpinBox)  # noqa: SLF001
    assert not tab.findChildren(QDateEdit)  # yearly selection only (requirement #8)


# -- ChartsTab: Matplotlib artists -------------------------------------------
def test_meter_chart_renders_all_points_as_line(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    lines = [ln for ln in tab._meter_view.axes.lines if isinstance(ln, Line2D)]
    assert lines and len(lines[0].get_xdata()) == len(dashboard.meter_series)  # nothing dropped
    assert lines[0].get_linestyle() == "-"


def test_usage_chart_is_line_series(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    assert len(tab._usage_view.axes.lines) >= 1  # requirement #15


def test_monthly_categories_are_mm_yyyy(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    labels = [label.get_text() for label in tab._monthly_view.axes.get_xticklabels()]
    assert labels and all(re.fullmatch(r"\d{2}/\d{4}", label) for label in labels)


def test_meter_card_zoom_opens_big_dialog(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    with mock.patch.object(BigChartDialog, "exec", return_value=0):
        tab._meter_card._open_big()  # noqa: SLF001


def test_charts_apply_language_translates_controls(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tr = Translator("en")
    tab = ChartsTab(tr, dark=False)
    tab.set_dashboard(dashboard)
    tr.set_language("de")
    tab.apply_language()
    assert tab._agg.itemText(tab._agg.findData(Aggregation.DAILY)) == "Täglich"  # noqa: SLF001
    assert tab._trend.text() == "Trend"  # noqa: SLF001
    # selection preserved
    preset_index = tab._preset.findData("all")  # noqa: SLF001
    tab._preset.setCurrentIndex(preset_index)  # noqa: SLF001
    assert tab._preset.itemText(preset_index) == "Alle"  # noqa: SLF001


def test_agg_combobox_propagates_to_controller(qapp, fake_repo, gas_repo):
    """AJAX review fix: aggregation is shared controller state, not a local render."""
    from app.presentation.dashboard_controller import DashboardController

    _seed(fake_repo)
    settings = FakeSettings({"app.unit": "m³"})
    logger = RecordingLogger()
    use_case = GetDashboardUseCase(fake_repo, gas_repo, settings, logger)
    controller = DashboardController(use_case, settings, logger, Translator("en"))
    tab = ChartsTab(Translator("en"), dark=False)
    emitted = []
    controller.charts_dashboard_changed.connect(emitted.append)
    tab.bind(controller)

    tab._agg.setCurrentIndex(tab._agg.findData(Aggregation.MONTHLY))  # noqa: SLF001
    assert controller._aggregation == Aggregation.MONTHLY  # noqa: SLF001
    assert emitted and emitted[-1].consumption[Aggregation.MONTHLY]

    # switching back to daily via the combo keeps controller state in sync
    tab._agg.setCurrentIndex(tab._agg.findData(Aggregation.DAILY))  # noqa: SLF001
    assert controller._aggregation == Aggregation.DAILY  # noqa: SLF001


def test_tooltip_builder_output(qapp):
    text = _tooltip_text(
        date(2026, 1, 2), Decimal("102"), Decimal("2"), Decimal("21.7"), Translator("en")
    )
    assert "2026-01-02" in text
    assert "m³" in text
    assert "kWh" in text


def test_big_chart_dialog_is_maximizable(qapp):
    """Requirement: the modal chart window can be maximized/resized."""
    dialog = BigChartDialog(MplRender(draw=lambda ax: None), "big", dark=False)
    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.WindowMaximizeButtonHint
    assert dialog.isSizeGripEnabled() is True
    dialog.deleteLater()


def test_light_mode_axis_labels_are_dark(qapp):
    """Light-mode charts must use dark text for readability."""
    from matplotlib import colors as mcolors
    from matplotlib.figure import Figure

    from app.presentation.mpl_charts import _TEXT_COLOR

    def label_color(dark: bool) -> str:
        fig = Figure()
        ax = fig.add_subplot(111)
        ax.set_xticks([0.5])
        ax.set_xticklabels(["x"])
        _style_axes(ax, dark=dark)
        return mcolors.to_hex(ax.get_xticklabels()[0].get_color())

    assert label_color(False).lower() == _TEXT_COLOR[False].lower()
    assert label_color(True).lower() == _TEXT_COLOR[True].lower()

    fig = Figure()
    ax = fig.add_subplot(111)
    _style_axes(ax, dark=False)
    assert mcolors.to_hex(ax.get_facecolor()) == "#ffffff"
    assert mcolors.to_hex(ax.figure.patch.get_facecolor()) == "#ffffff"


def test_meter_x_range_spans_query_days(qapp, fake_repo, gas_repo):
    """The meter x axis covers exactly the queried window (native date numbers)."""
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    lo, hi = tab._meter_view.axes.get_xlim()  # noqa: SLF001
    assert lo == _date2num(date(2026, 1, 1)) - 0.5
    assert hi == _date2num(date(2026, 1, 3)) + 0.5


def test_meter_chart_has_no_dashed_interpolation_overlay(qapp, fake_repo, gas_repo):
    """The grey dashed 'interpolated spans' line is gone (owner feedback)."""
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    lines = [ln for ln in tab._meter_view.axes.lines if isinstance(ln, Line2D)]
    assert len(lines) == 1  # only the solid meter line remains
    assert lines[0].get_linestyle() == "-"
    # normalized: the meter line starts at 0 and counts up like the compare view
    values = list(lines[0].get_ydata())
    assert values[0] == 0.0
    assert values == sorted(values)


def test_builders_return_render_with_targets(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tr = Translator("en")
    meter = _meter_chart_builder(dashboard.meter_series, dashboard.consumption[Aggregation.DAILY], False, tr)()
    assert isinstance(meter, MplRender)
    assert len(meter.targets) == len(dashboard.meter_series)
    usage = _usage_chart_builder(dashboard, Aggregation.DAILY, False, False, tr)()
    assert isinstance(usage, MplRender)
    assert len(usage.targets) == len(dashboard.consumption[Aggregation.DAILY])
    monthly = _monthly_chart_builder(dashboard, False, tr)()
    assert isinstance(monthly, MplRender)
    assert len(monthly.targets) == len(dashboard.consumption[Aggregation.MONTHLY])
    assert monthly.bar_hit is True


def test_card_views_are_matplotlib_canvases(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    assert isinstance(tab._meter_view, MplChartCanvas)  # noqa: SLF001
    assert isinstance(tab._monthly_view, MplChartCanvas)  # noqa: SLF001
    assert tab._meter_view._targets  # noqa: SLF001
    assert tab._monthly_view._targets  # noqa: SLF001


def test_nearest_target_pure(qapp):
    near = _HoverTarget(2.0, 2.0, "near")
    targets = [near, _HoverTarget(5.0, 5.0, "far")]
    assert _nearest_target(2.2, 2.1, targets, x_tol=1.0, y_tol=1.0) is near
    assert _nearest_target(3.5, 2.1, targets, x_tol=1.0, y_tol=1.0) is None  # x too far
    assert _nearest_target(2.1, 4.0, targets, x_tol=1.0, y_tol=1.0) is None  # y too far
    assert _nearest_target(10.0, 10.0, targets, x_tol=1.0, y_tol=1.0) is None
    assert _nearest_target(0.0, 0.0, [], x_tol=1.0, y_tol=1.0) is None


def test_charts_sync_pickers_from_presets(qapp, fake_repo, gas_repo):
    """AJAX: a chart preset must move the year spinboxes, not just the data."""
    from app.presentation.dashboard_controller import DashboardController

    _seed(fake_repo)
    settings = FakeSettings({"app.unit": "m³"})
    logger = RecordingLogger()
    today = date(2026, 2, 4)
    use_case = GetDashboardUseCase(fake_repo, gas_repo, settings, logger, clock=FixedClock(today))
    controller = DashboardController(use_case, settings, logger, Translator("en"), clock=FixedClock(today))
    tab = ChartsTab(Translator("en"), dark=False)
    tab.bind(controller)
    assert tab._preset.currentData() == "this_year"  # noqa: SLF001
    assert tab._year_from.value() == 2026  # noqa: SLF001
    assert tab._year_to.value() == 2026  # noqa: SLF001
    combo = tab._preset  # noqa: SLF001
    combo.setCurrentIndex(combo.findData("last3"))
    assert tab._year_from.value() == 2024  # noqa: SLF001
    assert tab._year_to.value() == 2026  # noqa: SLF001
    combo.setCurrentIndex(combo.findData("all"))
    assert controller.charts_resolved_years() == (2025, 2026)
    assert tab._year_from.value() == 2025  # noqa: SLF001
    assert tab._year_to.value() == 2026  # noqa: SLF001


def test_manual_year_change_switches_to_custom(qapp, fake_repo, gas_repo):
    from app.presentation.dashboard_controller import DashboardController

    _seed(fake_repo)
    settings = FakeSettings({"app.unit": "m³"})
    logger = RecordingLogger()
    today = date(2026, 2, 4)
    use_case = GetDashboardUseCase(fake_repo, gas_repo, settings, logger, clock=FixedClock(today))
    controller = DashboardController(use_case, settings, logger, Translator("en"), clock=FixedClock(today))
    tab = ChartsTab(Translator("en"), dark=False)
    tab.bind(controller)
    tab._year_from.setValue(2020)  # noqa: SLF001 - user edits the year
    assert tab._preset.currentData() is None  # noqa: SLF001
    assert controller.charts_resolved_years() == (2020, 2026)


def test_monthly_bar_labels_integer_no_notation(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    texts = [t.get_text() for t in tab._monthly_view.axes.texts if t.get_text()]
    assert texts, "bar value labels must be drawn"
    for text in texts:
        assert "e+" not in text and "E+" not in text
        assert bool(re.fullmatch(r"\d[\d.,]* m³", text))


def test_tooltip_persists_and_shows_on_click(qapp, fake_repo, gas_repo):
    """Owner: hover info stays until the mouse moves; a click shows it too."""
    _seed(fake_repo)
    dashboard = _dashboard(fake_repo, gas_repo, RecordingLogger())
    tab = ChartsTab(Translator("en"), dark=False)
    tab.set_dashboard(dashboard)
    tab.resize(800, 500)
    tab.show()
    qapp.processEvents()

    view = tab._meter_view
    # park the mouse away first, then move onto the second meter point
    _drive(view, "motion_notify_event", -1000, 0.0)
    qapp.processEvents()
    point = view._targets[1]  # noqa: SLF001
    _drive(view, "motion_notify_event", point.x, point.y)
    qapp.processEvents()
    assert view._target is not None  # noqa: SLF001
    assert view._info.get_visible()  # noqa: SLF001
    label_text = view._info.get_text()  # noqa: SLF001
    assert label_text

    # a Matplotlib annotation has no OS auto-hide: it must still be there after 3 s
    QTest.qWait(3000)
    qapp.processEvents()
    assert view._info.get_visible()  # noqa: SLF001

    view._hide()  # noqa: SLF001 - exactly what mouse-move-away / leave triggers
    qapp.processEvents()
    assert view._target is None  # noqa: SLF001
    assert not view._info.get_visible()  # noqa: SLF001

    # a click shows the same info through the identical path
    _drive(view, "button_press_event", point.x, point.y, button=1)
    qapp.processEvents()
    assert view._info.get_visible()  # noqa: SLF001
    assert view._info.get_text() == label_text  # noqa: SLF001
    view.close()


# -- Compare tab -----------------------------------------------------------------
def test_compare_tab_builds_exactly_two_years(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    meter = tab._meter_view  # noqa: SLF001
    usage = tab._usage_view  # noqa: SLF001
    monthly = tab._monthly_view  # noqa: SLF001
    # two overlaid lines (one per year) in both line charts
    meter_lines = [ln for ln in meter.axes.lines if isinstance(ln, Line2D)]
    usage_lines = [ln for ln in usage.axes.lines if isinstance(ln, Line2D)]
    assert len(meter_lines) == 2
    assert len(usage_lines) == 2
    for line in meter_lines:
        values = list(line.get_ydata())
        assert values == sorted(values)  # meter counts up over each year
    # both years share one FULL Jan-Dec axis (overlay year 2000), not a data range
    from app.presentation.compare import _OVERLAY_YEAR

    lo, hi = meter.axes.get_xlim()
    assert lo == _date2num(date(_OVERLAY_YEAR, 1, 1))
    assert hi == _date2num(date(_OVERLAY_YEAR, 12, 31))
    # two side-by-side bar sets (one per year), all 12 months aligned
    assert len(monthly.axes.containers) == 2
    assert [len(c.patches) for c in monthly.axes.containers] == [12, 12]
    assert monthly.axes.containers[0].get_label() == "2025"
    assert monthly.axes.containers[1].get_label() == "2026"


def test_compare_tab_values_labeled_and_unit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo, tr=Translator("en"))
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    labels = [t.get_text() for t in tab._monthly_view.axes.texts if t.get_text()]  # noqa: SLF001
    assert labels and all("m³" in text for text in labels)
    assert all("e+" not in text and "E+" not in text for text in labels)
    # 2026 has consumption in January (year B drawn blue on the LEFT half)
    assert tab._monthly_view.axes.containers[1].datavalues[0] > 0  # noqa: SLF001
    assert "m³" in tab._total_a_label.text()


def test_compare_tab_hover_targets_for_both_years(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    meter_targets = tab._meter_view._targets  # noqa: SLF001
    monthly_targets = tab._monthly_view._targets  # noqa: SLF001
    assert len(meter_targets) >= 2  # at least one point per year
    assert all(target.text for target in meter_targets)
    assert monthly_targets  # both years appear in the monthly tooltips
    texts = " ".join(target.text for target in monthly_targets)
    assert "2025" in texts and "2026" in texts


def test_compare_tooltip_shows_year_to_date(qapp, fake_repo, gas_repo):
    """Meter + usage hovers in Compare carry 'consumption since year start'."""
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo, tr=Translator("en"))
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    meter_text = " | ".join(t.text for t in tab._meter_view._targets)  # noqa: SLF001
    usage_text = " | ".join(t.text for t in tab._usage_view._targets)  # noqa: SLF001
    assert "Consumption since year start" in meter_text
    assert "Consumption since year start" in usage_text
    assert "m³" in meter_text and "kWh" in meter_text
    assert "m³" in usage_text and "kWh" in usage_text


def test_compare_tab_aggregation_changes_usage_chart(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001

    def point_counts():
        return [
            len(line.get_xdata())
            for line in tab._usage_view.axes.lines  # noqa: SLF001
            if isinstance(line, Line2D)
        ]

    daily_counts = point_counts()
    tab._agg_combo.setCurrentIndex(tab._agg_combo.findData(Aggregation.MONTHLY))  # noqa: SLF001
    monthly_counts = point_counts()
    assert daily_counts and monthly_counts
    # aggregation must reduce the total number of plotted points
    assert sum(monthly_counts) < sum(daily_counts)


def test_compare_tab_unit_combo_switches_unit(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    tab._unit_combo.setCurrentIndex(tab._unit_combo.findData(ViewUnit.KWH))  # noqa: SLF001
    assert tab._unit == ViewUnit.KWH
    assert tab._total_a_label.text().endswith("kWh")


def test_compare_tab_ignores_charts_filter(qapp, fake_repo, gas_repo):
    """Requirement: from/to does not apply - only year A/B decide."""
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2024)  # no data  # noqa: SLF001
    tab._year_b.setValue(2024)  # noqa: SLF001
    assert tab._empty_label.isHidden() is False  # "no data" hint visible
    assert tab._meter_view.isHidden() is True
    tab._year_a.setValue(2025)  # data returns  # noqa: SLF001
    assert tab._empty_label.isHidden() is True


def test_compare_monthly_hover_reads_the_hovered_bar(qapp, fake_repo, gas_repo):
    """Hover over the LEFT (blue, year B) and RIGHT (green, year A) Jan bars."""
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo, tr=Translator("en"))
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    tab.resize(1200, 800)
    tab.show()
    qapp.processEvents()
    view = tab._monthly_view  # noqa: SLF001

    # blue (2026) sits LEFT at x=-0.21, green (2025) RIGHT at x=+0.21
    _drive(view, "motion_notify_event", -0.21, 2.0)
    qapp.processEvents()
    assert view._target is not None and "01/2026" in view._target.text  # noqa: SLF001
    _drive(view, "motion_notify_event", 0.21, 1.5)
    qapp.processEvents()
    assert view._target is not None and "01/2025" in view._target.text  # noqa: SLF001
    tab.close()
    qapp.processEvents()


def test_compare_monthly_bar_targets_pick_correct_year(qapp, fake_repo, gas_repo):
    """Left (blue/2026) resolves to 01/2026, right (green/2025) to 01/2025."""
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    targets = tab._monthly_view._targets  # noqa: SLF001
    y_tol = tab._monthly_view._y_tol  # noqa: SLF001
    left = _bar_target_at(-0.1, 1.0, targets, y_tol)  # blue / 2026
    right = _bar_target_at(0.1, 1.0, targets, y_tol)  # green / 2025
    assert left is not None and right is not None
    assert "01/2026" in left.text
    assert "01/2025" in right.text
    assert left is not right


def test_compare_click_on_green_and_blue_bar(qapp, fake_repo, gas_repo):
    """Owner scenario: CLICK the green (01/2025) then the blue (01/2026) bar.

    The click must resolve the exact bar, show the info and highlight it.
    """
    _seed(fake_repo)
    tab = _compare_tab(fake_repo, gas_repo, tr=Translator("en"))
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    tab.resize(1200, 800)
    tab.show()
    qapp.processEvents()
    view = tab._monthly_view  # noqa: SLF001
    clicks = []
    view.set_click_logger(clicks.append)

    def click_and_assert(xd: float, yd: float, expected: str, bar_x: float) -> None:
        _drive(view, "button_press_event", xd, yd, button=1)
        qapp.processEvents()
        assert view._target is not None
        assert view._target.text.splitlines()[0] == expected
        assert view._info.get_visible()  # noqa: SLF001
        assert view._highlight.get_visible(), "clicked bar must be highlighted"
        # the highlight must cover exactly the clicked bar's data-space rect
        assert abs(view._highlight.get_x() - bar_x) < 1e-6  # noqa: SLF001

    click_and_assert(0.21, 1.5, "01/2025", 0.01)  # green / year A (drawn RIGHT)
    assert clicks and "Chart click" in clicks[-1] and "01/2025" in clicks[-1]
    click_and_assert(-0.21, 2.0, "01/2026", -0.41)  # blue / year B (drawn LEFT)
    assert clicks and "Chart click" in clicks[-1] and "01/2026" in clicks[-1]
    tab.close()
    qapp.processEvents()


def test_bar_hit_uses_drawn_bar_rects(qapp, fake_repo, gas_repo):
    """Owner scenario: mouse over February must highlight FEBRUARY (no shift)."""
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 2, 1), Decimal("110"))
    fake_repo.save_import(date(2026, 2, 2), Decimal("112"))
    fake_repo.save_import(date(2025, 1, 1), Decimal("80"))
    fake_repo.save_import(date(2025, 1, 2), Decimal("82"))
    fake_repo.save_import(date(2025, 2, 1), Decimal("90"))
    fake_repo.save_import(date(2025, 2, 2), Decimal("92"))
    tab = _compare_tab(fake_repo, gas_repo)
    tab._year_a.setValue(2025)  # noqa: SLF001
    tab._year_b.setValue(2026)  # noqa: SLF001
    tab.resize(1200, 800)
    tab.show()
    qapp.processEvents()
    view = tab._monthly_view  # noqa: SLF001

    # February green (2025) bar: right half of category 1 (x ~ 1.21)
    _drive(view, "motion_notify_event", 1.21, 1.0)
    qapp.processEvents()
    assert view._target is not None and "02/2025" in view._target.text, (
        f"mouse over Feb resolved to "
        f"{view._target.text.splitlines()[0] if view._target else None!r}"
    )
    assert view._highlight.get_visible()  # noqa: SLF001
    # highlight must sit over the February green bar (x in [1.01, 1.41])
    hx = view._highlight.get_x()  # noqa: SLF001
    assert 1.01 <= hx <= 1.41, f"highlight at x={hx:.2f}"

    # February blue (2026) bar: left half of category 1 (x ~ 0.79)
    _drive(view, "motion_notify_event", 0.79, 1.0)
    qapp.processEvents()
    assert view._target is not None and "02/2026" in view._target.text
    hx = view._highlight.get_x()  # noqa: SLF001
    assert 0.59 <= hx <= 0.99, f"highlight at x={hx:.2f}"
    tab.close()
    qapp.processEvents()
