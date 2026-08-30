# Implementation Plan — Replace QtCharts with Matplotlib

## Overview

Migrate every diagram from PyQt6-Charts to **Matplotlib**: the three Charts-tab cards (Zählerstand / Verbrauch / Monat) and all three Compare-tab charts (meter, usage, monthly). Matplotlib also takes over everything the previous rounds had to patch onto QtCharts — axis/bar labels, the mouse-hover info bubble, point/bar click detection, the orange highlight outline and the click log — because the PyQt6-Charts signal chain is dead in this environment and the owner explicitly asked for exactly this. Qt remains the application shell (`QApplication`, `QMainWindow`, `QTabWidget`, filter rows, table, dialogs, `KpiCard` labels); only the diagram widgets and their interactivity become Matplotlib `Figure` + `Axes` embedded on `FigureCanvasQTAgg`.

No behaviour is lost: normalized meter line starting at 0 (absolute meter value in the tooltip), daily/weekly/monthly usage with optional dashed trend, monthly bars with integer value labels inside the bars (no `1.8E+03`), two-year Compare overlay on a shared Jan–Dec axis, Compare monthly bars side by side, year-to-date hover suffix, theme-aware colours, double-click „Show in big", persistent hover info that disappears only on mouse-away/leave, click == hover. The controller/picker AJAX sync is untouched.

## Types

- `MplRender` (new, `app/presentation/mpl_charts.py`) replaces `ChartRender`:

  ```python
  @dataclass(frozen=True, slots=True)
  class MplRender:
      draw: Callable[[Axes], None]               # paints everything into the canvas axes
      targets: list[_HoverTarget] = field(default_factory=list)
      x_tol: float = 0.0
      y_tol: float = 0.0
      bar_hit: bool = False
  ```

  The `draw` closure captures `dark`, the `Translator`, series data and normalization; the canvas owns one `Figure`/`Axes` pair, clears it and calls `draw`, so presets/unit/agg/theme changes re-render on the same widget.
- `_HoverTarget` (unchanged `x / y / text` frozen dataclass) relocates from `charts.py` to `mpl_charts.py`; `charts.py` and `compare.py` import it back.
- Palette constants in `mpl_charts.py` (existing hex values): `_BG_COLOR = {True: "#1E1E1E", False: "#FFFFFF"}`, `_TEXT_COLOR = {True: "#E6E6E6", False: "#202020"}`, `_GRID_COLOR = {True: "#3C3C3C", False: "#D0D0D0"}`; plus module constants for the series accents `#FFB300` (highlight) and `#A00000` (trend), matching today's Qt values.
- Removed types: `ChartRender` and every `PyQt6.QtCharts` symbol (`QChart`, `QChartView`, `QLineSeries`, `QBarSeries`, `QBarSet`, `QBarCategoryAxis`, `QDateTimeAxis`, `QValueAxis`, `QAbstractBarSeries`).
- Kept unchanged: `Dashboard`, `MeterPoint`, `ConsumptionPoint`, `DashboardController`, `Translator`, `KpiCard` (plain Qt labels).

## Files

| File | Change |
|---|---|
| `app/presentation/mpl_charts.py` | **New.** Matplotlib canvas widget `MplChartCanvas`, `MplRender`, shared pure helpers (`_HoverTarget`, `_nearest_target`, `_line_tolerances`, `_bar_tolerances`, `_bar_target_at`, `_tooltip_text`) and the new matplotlib helpers (`_date2num`, `_style_axes`, `_add_datetime_axes`, `_bar_value_labels`). Forces `matplotlib.use("QtAgg")` at import top (before any figure creation). |
| `app/presentation/charts.py` | Strip all `PyQt6.QtCharts` imports/classes; builders return `MplRender`; `ChartCard`, `BigChartDialog`, `ChartsTab` embed `MplChartCanvas`. Delete `TooltipChartView`, `ChartRender`, `_epoch_ms`, `_to_qdatetime`, `_theme_bg`, `_apply_chart_text_colors`, `_make_chart`, Qt `_add_datetime_axes`, `_bar_pixel_rects`, `_bar_target_at_pixel`, `_configure_native_bar_labels`. |
| `app/presentation/compare.py` | Render builders → `MplRender`; `_overlay_ms` → `_overlay_num`; `_new_view` returns `MplChartCanvas`; helper imports from `mpl_charts`. |
| `requirements.txt` | Recreate from `git show HEAD:requirements.txt`: remove `PyQt6-Charts`, add `matplotlib>=3.11`. |
| `.github/workflows/release.yml` | PyInstaller call: drop `--hidden-import PyQt6.QtCharts`, add `--hidden-import matplotlib.backends.backend_qtagg`. |
| `.github/workflows/ci.yml` | Unchanged logic (pulls the recreated `requirements.txt`); re-run to confirm. |
| `README.md` | Replace QtCharts wording (Requirements, Features „Statistik & Diagramme", `Build & release`) with Matplotlib. |
| `tests/test_presentation/test_charts_smoke.py` | Rewrite chart assertions to matplotlib Axes/artists and real mouse events (details under Testing). |
| `tests/test_presentation/test_main_window.py` | Expected unchanged (picker/theme/table logic only); verify. |
| `_probe_*.py` (repo root) | Delete scratch probes (untracked, import PyQt6.QtCharts). |

## Functions

### New — `app/presentation/mpl_charts.py`

| Function | Purpose |
|---|---|
| `_date2num(day: date) -> float` | `mdates.date2num(day)`. Consecutive days are spaced 1.0 — the natural x data for every chart. |
| `_style_axes(ax, dark) -> None` | `ax.set_facecolor` + `ax.figure.patch.set_facecolor`, tick label colour from `_TEXT_COLOR`, spine colour, `ax.grid(True, color=_GRID_COLOR[dark])`. Called by every `draw` closure, so the canvas never needs the `dark` flag. |
| `_add_datetime_axes(ax, days, fmt, dark) -> None` | x locator/formatter (`%Y-%m-%d` daily, `%Y-%m` weekly+monthly, `%b` compare), `ax.set_xlim(min(days)..max(days))`, rotated ticks; calls `_style_axes`. |
| `_bar_value_labels(ax, container, unit_text, dark, tr) -> list[Text]` | One white bold label per bar, centered inside: `f"{tr.format_number(v, decimals=0)} {unit_text}"` (never scientific notation), skipped for zero/empty bars; usable for the single-set monthly chart and the two-set compare chart. |
| `_make_canvas(parent) -> MplChartCanvas` | Factory used by `ChartCard`, `CompareTab` and `BigChartDialog` so construction stays identical (canvas + min height + expanding size policy). |

### New — event handlers on `MplChartCanvas` (documented under Classes)

### Modified — `app/presentation/charts.py`

| Function | Required change |
|---|---|
| `_meter_targets(points, daily_by_day, tr, base)` | x from `_epoch_ms` → `_date2num(point.day)`; y and tooltip text unchanged. |
| `_usage_targets(points, meter_by_day, unit, tr)` | Same x change. |
| `_meter_chart_builder(points, daily, dark, tr) -> MplRender` | Draw exactly **one** solid `Line2D` with visible markers, normalized `y = display − points[0].display_value` (starts at 0, monotone). Targets/tolerances from `_meter_targets`. No dashed overlay. |
| `_usage_chart_builder(dashboard, agg, trend_on, dark, tr) -> MplRender` | One usage `Line2D`; plus a dashed `#A00000` trend `Line2D` when `trend_on` and `dashboard.trendline`. Targets per usage point. |
| `_monthly_chart_builder(dashboard, dark, tr) -> MplRender` | One `ax.bar` container (x = 0..n−1, tick labels `%m/%Y`), integer labels via `_bar_value_labels`, targets per month at `(index, value)`, `bar_hit=True`, `x_tol=0.5`, `y_tol=_bar_tolerances(values)`. |

### Modified — `app/presentation/compare.py`

| Function | Required change |
|---|---|
| `_overlay_num(day: date) -> float` | Replaces `_overlay_ms`: `_date2num(date(2000, day.month, day.day))`. |
| `_compare_meter_render(dash_a, dash_b, year_a, year_b, dark, tr) -> MplRender` | Two overlaid lines, each normalized to 0 on Jan 1; shared Jan–Dec axes (`DateFormatter("%b")`, xlim Jan 1..Dec 31); targets per point with `_tooltip_text` + `_year_to_date_suffix`. |
| `_compare_usage_render(dash_a, dash_b, year_a, year_b, agg, dark, tr) -> MplRender` | Same overlay for the usage buckets of both years. |
| `_compare_monthly_render(dash_a, dash_b, year_a, year_b, dark, tr) -> MplRender` | Two `ax.bar` sets side by side (width 0.4, `x = cat ± 0.21`, draw order reproduces today's left/right mapping); integer labels; targets at each bar centre (`x = month−1 + (2·set+1)/(2·sets)`), `x_tol = 1/(2·sets) − 0.001`, `y_tol = _bar_tolerances(...)`, `bar_hit=True`. |

### Removed

- `charts.py`: `TooltipChartView`, `ChartRender`, `_epoch_ms`, `_to_qdatetime`, `_theme_bg`, `_apply_chart_text_colors`, `_make_chart`, Qt `_add_datetime_axes`, `_bar_pixel_rects`, `_bar_target_at_pixel`, `_configure_native_bar_labels`.
- `compare.py`: `_overlay_ms`, `_add_overlay_axes` (both replaced inside the draw closures).

## Classes

### New — `MplChartCanvas(FigureCanvasQTAgg)` in `app/presentation/mpl_charts.py`

- `__init__(parent=None)`: import `from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg`; create `Figure()` + `self.axes = figure.add_subplot(111)`; `super().__init__(figure)`; `self.setMouseTracking(True)`; state holds `_targets`, `_x_tol`, `_y_tol`, `_bar_hit`, `_target`, `_render`, `_double_click_callback`, `_click_logger`; wire `self.mpl_connect("motion_notify_event", self._on_motion)`, `"button_press_event", self._on_press`, `"figure_leave_event", self._on_leave`; create a hidden `ax.annotate` info box (round bbox `#2B2B2B`, white text) and a hidden `ax.add_patch(Rectangle)` highlight (`#FFB300`, `fill=False`, `lw=2.5`, near-max zorder).
- `store_interaction(render: MplRender) -> None` — `self.axes.clear()`; `render.draw(self.axes)`; reset annotation/highlight to hidden; `draw_idle()`.
- `_on_motion(event)` — when `event.inaxes is self.axes` and `xdata`/`ydata` are not None: resolve `_bar_target_at(...)` (bar charts) else `_nearest_target(...)`; show the info or `_hide()`.
- `_on_press(event)` — left button only; same resolution; on hit show persistent info + orange highlight; when `_click_logger` is set log `"Chart click viewport=(x0,y0) -> <first line of info text>"` (keeps the Protokoll-tab debugging aid).
- `_show_target(target)` / `_hide()` — update annotation text/position (offset above-right of the point/bar), toggle highlight visibility; `_target` stays readable for tests. Info persists until `_hide()` (mouse-away / leave) — no auto-hide timer.
- `mouseDoubleClickEvent(event)` — fires `_double_click_callback` („Show in big"); `set_double_click_callback(cb)`; `set_click_logger(cb)`.

### Modified

- `ChartCard(QWidget)` — `self.view = MplChartCanvas(self)` (drop the `QPainter`/`QChartView` hints); `set_chart(builder, title)` → `self.view.store_interaction(builder())`; `_open_big()` unchanged (double-click handler is wired on the canvas).
- `BigChartDialog(QDialog)` — same flags/resize/size grip; inner widget is `MplChartCanvas`; `store_interaction(render)`.
- `ChartsTab(QWidget)` — `_meter_view`/`_usage_view`/`_monthly_view` are `MplChartCanvas`; `_render`, `_sync_widgets`, `_render_meter/usage/monthly`, `apply_theme`, `apply_language` logic unchanged; `_empty_label` overlay stays.
- `CompareTab(QWidget)` — `_new_view` returns `MplChartCanvas`; `_recompute` calls `store_interaction(...)` on the three views; `apply_theme(dark)` re-renders all three; click logger wiring unchanged.
- `KpiCard` — unchanged (plain/rich Qt labels, not a diagram).

### Removed

- `TooltipChartView(QChartView)` — fully replaced by `MplChartCanvas`. The Qt hover/click/pixel-arcade machinery (`mapToValue`, `_bar_pixel_rects`, `_bar_target_at_pixel`, `QToolTip`) is gone.

## Dependencies

- `requirements.txt` (recreate from `git show HEAD:requirements.txt`): remove `PyQt6-Charts`, add `matplotlib>=3.11`. `numpy` resolves to 2.4.x through matplotlib (needs >= 1.25); app code never imports numpy, so the major-version jump is inert here.
- `release.yml` PyInstaller: remove `--hidden-import PyQt6.QtCharts`, add `--hidden-import matplotlib.backends.backend_qtagg`. PyInstaller's built-in matplotlib hook bundles `mpl-data`; the CI build must be run once to confirm the one-file `.exe` starts.
- README updates under Requirements / Features / Build & release.

## Testing

Baseline 273 tests green (matplotlib not installed yet). Strategy:

- `tests/test_presentation/test_charts_smoke.py` — rework chart assertions to matplotlib:
  - Builders return `MplRender`; each `render.draw(ax)` on a throwaway `Figure` produces the expected artists.
  - Meter: exactly one `Line2D`, solid, y starts at 0 and is monotone, x range == the queried date range; target count == meter point count.
  - Usage: one `Line2D`, plus a second dashed trend line when `trend_on`.
  - Monthly: one bar container; integer `Text` labels ending with the unit, no `e+`/`E+`; tick labels `MM/YYYY`; `bar_hit=True`; one target per month.
  - Compare: two meter lines, two usage lines, two bar containers; overlaid Jan–Dec x axis spans Jan 1..Dec 31.
  - Pure-logic tests stay: `_nearest_target`, `_line_tolerances`, `_bar_tolerances`, `_bar_target_at`, `_tooltip_text`.
  - Hover/click (`tooltip persists, click shows info`): real `QTest.mouseMove(canvas, QPoint)` / `QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos)`; assert `canvas._target` matches, annotation visible, still visible after `qWait(3000)` (no auto-hide), `_hide()` hides again, and the click log callback received a `Chart click ...` line.
  - Compare bar hover: mouse over the Jan-2025 vs Jan-2026 bar → `01/2025` resp. `01/2026` in `_target.text`, and (after a click) the highlight rectangle is centred over the clicked bar.
  - Theme: tick label colour via `ax.xaxis.get_ticklabels()[0].get_color()` in light vs dark.
  - Controller/picker tests (`test_charts_sync_pickers_from_presets`, `test_manual_year_change_switches_to_custom`, `test_agg_combobox_propagates_to_controller`) are copied unchanged.
  - Qt-only tests (`test_charts_x_values_are_epoch_millis`, `test_value_labels_round_to_integer_without_notation`, `test_native_bar_labels_render_value_with_unit`, `test_light_mode_axis_labels_are_dark`, `test_tooltip_persists_and_shows_on_click`) are replaced by the equivalent matplotlib assertions above.
- `tests/test_presentation/test_main_window.py` — expected green without edits (pickers/theme/table only); run to confirm.
- Domain/application/infrastructure suites — untouched.
- Validation commands: `python -m pytest tests/ -q` (offscreen is set in conftest) and `ruff check app/ tests/`.
- Manual Windows E2E: hover/click on all six charts shows the info box and orange highlight; theme switch light/dark recolours figures live; presets move the pickers; monthly bar labels integer; double-click opens the resizable big dialog; Compare bar halves show their own month/year.
- Optional: local `pyinstaller --onefile --windowed --name GasmeterDownloader --hidden-import matplotlib.backends.backend_qtagg --hidden-import github_updater app/main.py` smoke launch.

## Implementation Order

1. Recreate `requirements.txt` (`git show HEAD:requirements.txt` → remove `PyQt6-Charts`, add `matplotlib>=3.11`), `pip install -r requirements.txt`, sanity `python -c "import matplotlib; print(matplotlib.__version__)"`.
2. Add `app/presentation/mpl_charts.py` (helpers + `MplRender` + `MplChartCanvas`) — no callers yet.
3. Rewrite the `charts.py` builders to `MplRender`; swap `ChartCard`/`BigChartDialog`/`ChartsTab` to the canvas; delete the Qt hooks and `_probe_*.py`.
4. Rewrite `compare.py` render builders + `CompareTab._new_view`.
5. Rework `test_charts_smoke.py` to matplotlib assertions; run the full suite and iterate to green.
6. Update `release.yml` and README; final `pytest` + `ruff`; manual Windows E2E; optional PyInstaller smoke build.

## Assumptions & decisions

- The info bubble is a Matplotlib `ax.annotate` (owner wants labels/hovers/clicks in Matplotlib), persistent until mouse-away/leave; click == hover; click logging to the Protokoll tab exactly as today.
- No embedded Matplotlib navigation toolbar: the existing UX (double-click → resizable „Show in big" dialog) is kept; adding toolbar buttons would change the UI without a request.
- `KpiCard` and the table stay Qt widgets (they are not diagrams).
- `MplRender.draw(ax)` styles the axes itself (including `ax.figure.patch`), so the canvas never needs the `dark` flag.
- Compare keeps the shared Jan–Dec overlay built on `mdates.date2num(date(2000, month, day))` (Feb 29-safe).
- `requirements.txt` content is recovered from git; `implementation_plan.md` history is replaced by this revision.

## Implementation status — COMPLETE (2026-08-30, validated)

Executed exactly per this plan; final state:

- **Suite:** `python -m pytest tests/ -q` → **271 passed** (was 273; the old Qt-chart smoke file had 37 tests, the Matplotlib rewrite 35 — two Qt-native-label-only tests were replaced by Matplotlib label tests, all other coverage kept).
- **Lint:** `ruff check app/ tests/` → **All checks passed!**
- `requirements.txt` recreated: **PyQt6-Charts removed, `matplotlib>=3.11` added** (numpy auto-upgraded 1.24.1 → 2.4.6; app code never imports numpy). `release.yml` now uses `--hidden-import matplotlib.backends.backend_qtagg`; README updated. Scratch `_probe_*.py` files (and the old Qt probes) deleted; **zero `PyQt6.QtCharts` references remain in app/ and tests/**.
- Hover/click/labels/highlight/logging all live in Matplotlib (`MplChartCanvas`: `motion_notify_event`/`button_press_event`/`figure_leave_event`, persistent `ax.annotate` bubble, orange `Rectangle` highlight in data space). Click logging to the Protokoll tab verified end-to-end: `Chart click viewport=(154,107) -> 01/2026`.

Documented deviations (intentional, tested):

1. **Offscreen event injection:** the deterministic tests drive events through Matplotlib's own callback pipeline (`MouseEvent` + `canvas.callbacks.process` with data coordinates computed via `axes.transData`) instead of `QTest.mouseMove` rounding-trips. The Qt-widget→figure pixel conversion is DPI-scaled in the offscreen QPA platform, while Matplotlib's conversion is self-consistent for a real mouse (rendering and hit-testing share the same transform). Manual E2E on Windows is the real-mouse verification.
2. **`_bar_target_at` rounds to the nearest category** (`floor(vx + 0.5)`), so the Compare tab's left-half bars (`month − 1 − 0.21`) resolve to their own month instead of being dropped by the old `floor(vx)`/`<0` guard.
3. **Bar highlight via `_bar_rect_at`** — a pure data-space scan of the drawn `Rectangle`s (highlight self-excluded), replacing the Qt viewport-pixel machinery; mouse position and highlight can never diverge in data space.
4. The old Qt-only tests `test_value_labels_round_to_integer_without_notation` / `test_native_bar_labels_render_value_with_unit` were replaced by `test_monthly_bar_labels_integer_no_notation` (integer + unit, no `e+`) and the compare label/unit asserts; `test_bar_pixel_hit_matches_mouse_position` became `test_bar_hit_uses_drawn_bar_rects` (Feb green/blue with exact highlight x).

Everything from the plan is otherwise unchanged: `MplRender.draw(ax)` styles the axes itself (fig.patch included), KPI cards/table stay Qt, no navigation toolbar was added, Compare keeps the shared Jan–Dec overlay, and the AJAX picker sync was untouched.