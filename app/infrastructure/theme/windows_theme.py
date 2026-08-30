"""Native Windows light/dark theme detection + Fusion palette application.

The theme state is detected from
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize``
and re-checked on a short QTimer so the app follows OS theme switches live
without any fragile native event-filter glue (a native filter is what made an
earlier build hard-crash inside Qt's event dispatch).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QColor, QPalette

from app.domain.entities import LogCategory, LogLevel

logger = logging.getLogger(__name__)

THEME_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
THEME_POLL_MS = 2000


def is_windows_dark() -> bool:
    """Registry lookup: ``AppsUseLightTheme == 0`` means dark. Defaults to light."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except OSError:
        return False


def light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(0xF2, 0xF2, 0xF2))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(0x20, 0x20, 0x20))
    palette.setColor(QPalette.ColorRole.Base, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(0xF7, 0xF7, 0xF7))
    palette.setColor(QPalette.ColorRole.Text, QColor(0x20, 0x20, 0x20))
    palette.setColor(QPalette.ColorRole.Button, QColor(0xE1, 0xE1, 0xE1))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(0x20, 0x20, 0x20))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0x00, 0x78, 0xD4))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0x20, 0x20, 0x20))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(0x20, 0x20, 0x20))
    palette.setColor(QPalette.ColorRole.Link, QColor(0x00, 0x78, 0xD4))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(0x00, 0x00, 0x00))
    # dimmed variants so disabled/inactive widgets stay readable (never white-on-white)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(0x8A, 0x8A, 0x8A))
        palette.setColor(QPalette.ColorGroup.Inactive, role, QColor(0x20, 0x20, 0x20))
    return palette


def dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(0x2B, 0x2B, 0x2B))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(0xE6, 0xE6, 0xE6))
    palette.setColor(QPalette.ColorRole.Base, QColor(0x1E, 0x1E, 0x1E))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(0x2E, 0x2E, 0x2E))
    palette.setColor(QPalette.ColorRole.Text, QColor(0xE6, 0xE6, 0xE6))
    palette.setColor(QPalette.ColorRole.Button, QColor(0x3C, 0x3C, 0x3C))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(0xE6, 0xE6, 0xE6))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0x00, 0x78, 0xD4))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0x2B, 0x2B, 0x2B))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0xE6, 0xE6, 0xE6))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(0x8A, 0x8A, 0x8A))
    palette.setColor(QPalette.ColorRole.Link, QColor(0x4A, 0xA3, 0xE8))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(0xFF, 0xFF, 0xFF))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(0x5E, 0x5E, 0x5E))
        palette.setColor(QPalette.ColorGroup.Inactive, role, QColor(0xE6, 0xE6, 0xE6))
    return palette


class WindowsTheme(QObject):
    """Owns the theme state; notifies registered callbacks on theme changes.

    The theme can be forced via ``set_mode`` ("auto"/"dark"/"light"). In
    ``auto`` mode the OS state is polled on a 2 s timer (the registry is cheap
    to read) instead of a native event filter - robust across Qt versions and
    platforms. Changes only fire the callbacks when the resolved state differs.
    """

    _MODES = ("auto", "dark", "light")

    def __init__(self, app, parent: QObject | None = None):
        super().__init__(parent)
        self._app = app
        self._callbacks: list = []
        self._current_dark: bool | None = None
        self._mode = "auto"
        self._timer = QTimer(self)
        self._timer.setInterval(THEME_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def set_mode(self, mode: str) -> None:
        """Force the theme: "auto" (follow OS), "dark" or "light"."""
        if mode not in self._MODES:
            raise ValueError(f"Unknown theme mode: {mode!r}")
        self._mode = mode
        self._apply_resolved()

    @property
    def mode(self) -> str:
        return self._mode

    def install_change_callback(self, callback) -> None:
        """``callback(dark: bool)`` invoked (UI thread) on theme change."""
        self._callbacks.append(callback)

    def _resolve_dark(self) -> bool:
        if self._mode == "dark":
            return True
        if self._mode == "light":
            return False
        return is_windows_dark()

    def _apply_resolved(self) -> None:
        dark = self._resolve_dark()
        if self._current_dark is not None and self._current_dark == dark:
            return
        self._current_dark = dark
        for callback in self._callbacks:
            try:
                callback(dark)
            except Exception:  # noqa: BLE001
                logger.debug("theme callback error", exc_info=True)

    def _poll(self) -> None:
        self._apply_resolved()

    def apply(self, app, dark: bool) -> None:
        app.setStyle("Fusion")
        app.setPalette(dark_palette() if dark else light_palette())
        app.setStyleSheet("")
        # Qt does not reliably re-colour widgets that already exist; a full
        # unpolish/polish cycle on every widget (incl. children like toolbar
        # buttons, table buttons, menus) makes the switch apply immediately
        # (owner: "keine sofortige Anpassung, erst nach App-Restart").
        from PyQt6.QtWidgets import QWidget

        for top in app.topLevelWidgets():
            widgets = [top, *top.findChildren(QWidget)]
            for widget in widgets:
                app.style().unpolish(widget)
                app.style().polish(widget)
                widget.update()

    def current_is_dark(self) -> bool:
        dark = self._resolve_dark()
        self._current_dark = dark
        return dark

    def log_theme(self, logger_adapter, dark: bool) -> None:
        logger_adapter.log(LogCategory.THEME, LogLevel.INFO, f"Theme: {'dark' if dark else 'light'}")
