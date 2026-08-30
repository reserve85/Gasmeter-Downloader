"""Matplotlib chart canvas — replaces PyQt6-Charts app-wide.

Every chart is described by an :class:`MplRender` whose ``draw`` closure paints
into the single ``Axes`` owned by an :class:`MplChartCanvas`. The canvas handles
the interactivity in Matplotlib-native ways (owner: labels, hovers and clicks in
Matplotlib, not Qt): it listens to the Qt backend's mouse events, resolves the
nearest ``_HoverTarget`` in *data space* and keeps a persistent annotation info
bubble alive until the mouse moves away or leaves the figure. A click shows the
same info and (when wired) logs the click into the Protokoll tab.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import matplotlib

matplotlib.use("QtAgg")

from matplotlib import dates as mdates  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from PyQt6.QtWidgets import QSizePolicy, QWidget  # noqa: E402

from app.presentation.i18n import Translator  # noqa: E402

#: explicit colors so charts stay readable in light AND dark mode
_BG_COLOR = {True: "#1E1E1E", False: "#FFFFFF"}
_TEXT_COLOR = {True: "#E6E6E6", False: "#202020"}
_GRID_COLOR = {True: "#3C3C3C", False: "#D0D0D0"}
_SERIES_COLOR = "#2E7D32"  # main green line/bars
_COMPARE_COLORS = ("#2E7D32", "#1565C0")  # year A green / year B blue
_TREND_COLOR = "#A00000"
_HIGHLIGHT_COLOR = "#FFB300"


@dataclass(frozen=True, slots=True)
class _HoverTarget:
    """One hoverable spot: value coordinates plus the tooltip text to show."""

    x: float
    y: float
    text: str


@dataclass(frozen=True, slots=True)
class MplRender:
    """Fresh render instructions plus the interactivity metadata the canvas needs.

    ``draw`` paints the complete chart (data, axes styling incl. figure
    facecolor, legend) into any given ``Axes``; the canvas calls it after
    clearing its own axes, so unit/agg/preset/theme changes re-render on the
    same widget.
    """

    draw: Callable[[Axes], None]
    targets: list[_HoverTarget] = field(default_factory=list)
    x_tol: float = 0.0
    y_tol: float = 0.0
    bar_hit: bool = False


def _nearest_target(
    vx: float,
    vy: float,
    targets: list[_HoverTarget],
    x_tol: float,
    y_tol: float,
) -> _HoverTarget | None:
    """Nearest target inside both tolerance bands, or ``None`` when hovering nowhere."""
    if not targets:
        return None
    best: _HoverTarget | None = None
    best_distance = float("inf")
    for target in targets:
        dx = abs(target.x - vx)
        dy = abs(target.y - vy)
        if dx <= x_tol and dy <= y_tol:
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best = target
                best_distance = distance
    return best


def _line_tolerances(points_x: list[float], points_y: list[float]) -> tuple[float, float]:
    """Snap window for line charts: half the median x spacing, 12 % of the y range."""
    if not points_x:
        return 0.0, 0.0
    ordered = sorted(points_x)
    spacings = [b - a for a, b in zip(ordered, ordered[1:])]
    if spacings:
        x_tol = sorted(spacings)[len(spacings) // 2] / 2.0
    else:
        x_tol = (ordered[-1] - ordered[0]) * 0.5 or 1.0
    y_range = max(points_y) - min(points_y)
    return float(x_tol), max(y_range * 0.12, 1e-9)


def _bar_tolerances(values: list[float]) -> float:
    """Vertical snap window for bar charts: hovering anywhere over a column counts."""
    return max(values) if values else 0.0


def _bar_target_at(vx: float, vy: float, targets: list[_HoverTarget], y_tol: float) -> _HoverTarget | None:
    """Category-based bar hit test (data-space; nearest-category grouping).

    ``vx`` is rounded to the nearest category so side-by-side bars that sit at
    ``month - 1 ± 0.21`` (compare) and single bars at ``month - 1`` (monthly)
    both resolve to the same month column.
    """
    category = int(math.floor(vx + 0.5))
    if category < 0:
        return None
    cat_targets = [t for t in targets if int(math.floor(t.x + 0.5)) == category]
    if not cat_targets:
        return None
    max_y = max(t.y for t in cat_targets)
    fudge = max(max_y * 0.3, y_tol * 0.1, 1e-9)
    if vy < -fudge or vy > max_y + fudge:
        return None
    return min(cat_targets, key=lambda t: abs(t.x - vx))


def _bar_rect_at(ax: Axes, vx: float, vy: float, exclude: Rectangle | None = None) -> Rectangle | None:
    """The drawn bar whose data-space rect contains ``(vx, vy)`` (or ``None``).

    Because the highlight is itself a ``Rectangle`` in ``ax.patches``, it is
    excluded explicitly so a live highlight can never be re-selected.
    """
    fudge = 1e-9
    for patch in ax.patches:
        if not isinstance(patch, Rectangle) or patch is exclude:
            continue
        left, bottom = patch.get_x(), patch.get_y()
        width, height = patch.get_width(), patch.get_height()
        if (
            left - fudge <= vx <= left + width + fudge
            and bottom - fudge <= vy <= bottom + height + fudge
        ):
            return patch
    return None


def _tooltip_text(day: date, meter_m3, delta_m3, delta_kwh, tr: Translator, monthly: bool = False) -> str:
    """Shared hover/click text: Datum / Zählerstand / Verbrauch (m³ + kWh)."""
    if monthly:
        return (
            f"{day.strftime('%m/%Y')}\n"
            f"{tr.t('charts.tt.usage_month')}: {tr.format_number(delta_m3)} m³\n"
            f"{tr.format_number(delta_kwh)} kWh"
        )
    return (
        f"{tr.t('charts.tt.date')}: {tr.format_date(day)}\n"
        f"{tr.t('charts.tt.meter')}: {tr.format_number(meter_m3)} m³\n"
        f"{tr.t('charts.tt.usage_day')}: {tr.format_number(delta_m3)} m³ / "
        f"{tr.format_number(delta_kwh)} kWh"
    )


def _date2num(day: date) -> float:
    """Matplotlib date-number for ``day`` (consecutive days are spaced 1.0)."""
    return float(mdates.date2num(day))


def _style_axes(ax: Axes, dark: bool) -> None:
    """Pin theme colors for the axes, its figure and the grid."""
    bg = _BG_COLOR[dark]
    text = _TEXT_COLOR[dark]
    ax.set_facecolor(bg)
    ax.figure.patch.set_facecolor(bg)
    ax.tick_params(colors=text, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(text)
    ax.grid(True, color=_GRID_COLOR[dark], linewidth=0.6, alpha=0.7)


def _add_datetime_axes(ax: Axes, days: list[date], fmt: str, dark: bool) -> None:
    """Date-formatted x axis spanning ``days``; ticks rotate for daily ranges."""
    _style_axes(ax, dark)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=8))
    if fmt == "%Y-%m-%d":
        ax.tick_params(axis="x", rotation=15)
    if days:
        lo = min(_date2num(d) for d in days)
        hi = max(_date2num(d) for d in days)
        ax.set_xlim(lo - 0.5, hi + 0.5)


def _bar_value_labels(ax: Axes, container, unit_text: str, dark: bool, tr: Translator) -> list[Text]:
    """One white bold integer label per bar, centered inside the bar.

    Zero/empty bars get no label; bars too small to hold the text get the label
    *above* the bar in the theme text color (so light mode never shows white on
    white). Labels are laid out in data space and never use scientific notation.
    """
    texts: list[Text] = []
    values = list(container.datavalues) if container.datavalues is not None else []
    for patch, value in zip(container.patches, values):
        if not value:
            continue
        label = f"{tr.format_number(Decimal(str(value)), decimals=0)} {unit_text}"
        center_x = patch.get_x() + patch.get_width() / 2
        if patch.get_height() >= 12:
            text = ax.text(
                center_x,
                patch.get_y() + patch.get_height() / 2,
                label,
                ha="center",
                va="center",
                color="#FFFFFF",
                fontsize=8,
                fontweight="bold",
                zorder=10,
                clip_on=False,
            )
        else:
            text = ax.text(
                center_x,
                patch.get_y() + patch.get_height() + 6,
                label,
                ha="center",
                va="bottom",
                color=_TEXT_COLOR[dark],
                fontsize=8,
                fontweight="bold",
                zorder=10,
                clip_on=False,
            )
        texts.append(text)
    return texts


class MplChartCanvas(FigureCanvasQTAgg):
    """One Matplotlib figure with working hover/click info + bar highlight.

    Events come from the QtAgg backend: ``motion_notify_event`` (hover),
    ``button_press_event`` (click == hover, plus optional click logging) and
    ``figure_leave_event``. The info bubble is a Matplotlib ``Axes.annotate``
    artist that stays visible until the mouse moves away/leaves (no auto-hide;
    the owner explicitly wants persistent info). Bars get a persistent orange
    outline drawn over the *same* data-space rectangle that was hit, so mouse
    position and highlight can never diverge.
    """

    def __init__(self, parent: QWidget | None = None):
        self._figure = Figure(figsize=(6, 3), dpi=100)
        self.axes = self._figure.add_subplot(111)
        super().__init__(self._figure)
        if parent is not None:
            self.setParent(parent)
        self.setMouseTracking(True)
        self._render: MplRender | None = None
        self._targets: list[_HoverTarget] = []
        self._x_tol = 0.0
        self._y_tol = 0.0
        self._bar_hit = False
        self._target: _HoverTarget | None = None
        self._info: Text | None = None
        self._highlight: Rectangle | None = None
        self._double_click_callback: Callable[[], None] | None = None
        self._click_logger: Callable[[str], None] | None = None
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("figure_leave_event", self._on_leave)

    # -- public API -------------------------------------------------------------
    def store_interaction(self, render: MplRender) -> None:
        """Attach ``render`` (draw closure + tooltip metadata) to this canvas."""
        self._render = render
        self.axes.clear()
        render.draw(self.axes)
        self._targets = render.targets
        self._x_tol = render.x_tol
        self._y_tol = render.y_tol
        self._bar_hit = render.bar_hit
        self._info = self.axes.annotate(
            "",
            xy=(0, 0),
            xytext=(8, 10),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.35",
                "fc": "#2B2B2B",
                "ec": "#555555",
                "lw": 1.0,
                "alpha": 0.95,
            },
            color="#FFFFFF",
            fontsize=9,
            zorder=300,
            visible=False,
        )
        self._highlight = self.axes.add_patch(
            Rectangle(
                (0, 0),
                0,
                0,
                fill=False,
                edgecolor=_HIGHLIGHT_COLOR,
                linewidth=2.5,
                zorder=250,
                visible=False,
            )
        )
        self._hide()
        self.draw_idle()

    def set_double_click_callback(self, callback: Callable[[], None]) -> None:
        """Optional action on double-click (e.g. open the big dialog)."""
        self._double_click_callback = callback

    def set_click_logger(self, logger_callback: Callable[[str], None]) -> None:
        """Optional log hook: receives a human-readable line per LEFT click."""
        self._click_logger = logger_callback

# -- event handling -----------------------------------------------------------
    def _on_motion(self, event) -> None:
        if event.inaxes is not self.axes or event.xdata is None or event.ydata is None:
            self._hide()
            return
        target = self._resolve(float(event.xdata), float(event.ydata))
        if target is None:
            self._hide()
        else:
            self._show(target, float(event.xdata), float(event.ydata))

    def _on_press(self, event) -> None:
        if event.button != 1 or event.inaxes is not self.axes or event.xdata is None:
            return
        target = self._resolve(float(event.xdata), float(event.ydata))
        if target is None:
            self._hide()
            return
        self._show(target, float(event.xdata), float(event.ydata))
        if self._click_logger is not None:
            self._click_logger(
                f"Chart click viewport=({event.x:.0f},{event.y:.0f}) -> "
                f"{target.text.splitlines()[0]}"
            )

    def _on_leave(self, event) -> None:
        self._hide()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._double_click_callback is not None:
            self._double_click_callback()
        else:
            super().mouseDoubleClickEvent(event)

    # -- internals ----------------------------------------------------------------
    def _resolve(self, vx: float, vy: float) -> _HoverTarget | None:
        if self._bar_hit:
            return _bar_target_at(vx, vy, self._targets, self._y_tol)
        return _nearest_target(vx, vy, self._targets, self._x_tol, self._y_tol)

    def _show(self, target: _HoverTarget, xd: float, yd: float) -> None:
        if target is self._target:
            return  # already showing the same point
        self._target = target
        if self._info is not None:
            self._info.set_text(target.text)
            self._info.xy = (xd, yd)
            # flip the bubble near the top/right edge so it stays visible
            xmin, xmax = self.axes.get_xlim()
            ymin, ymax = self.axes.get_ylim()
            fx = (xd - xmin) / max(xmax - xmin, 1e-9)
            fy = (yd - ymin) / max(ymax - ymin, 1e-9)
            dx = -8 if fx > 0.75 else 8
            dy = -8 if fy > 0.8 else 10
            self._info.xytext = (dx, dy)
            self._info.set_visible(True)
        self._update_highlight(xd, yd)
        self.draw_idle()

    def _update_highlight(self, xd: float, yd: float) -> None:
        if self._highlight is None:
            return
        rect = _bar_rect_at(self.axes, xd, yd, exclude=self._highlight) if self._bar_hit else None
        if rect is None:
            if self._highlight.get_visible():
                self._highlight.set_visible(False)
            return
        self._highlight.set_xy((rect.get_x(), rect.get_y()))
        self._highlight.set_width(rect.get_width())
        self._highlight.set_height(rect.get_height())
        self._highlight.set_visible(True)

    def _hide(self) -> None:
        if self._info is not None and self._info.get_visible():
            self._info.set_visible(False)
        if self._highlight is not None and self._highlight.get_visible():
            self._highlight.set_visible(False)
        self._target = None


def _make_canvas(parent: QWidget | None, min_height: int = 180) -> MplChartCanvas:
    """Standard canvas with the app-wide sizing policy (used by all chart widgets)."""
    canvas = MplChartCanvas(parent)
    canvas.setMinimumHeight(min_height)
    canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return canvas
