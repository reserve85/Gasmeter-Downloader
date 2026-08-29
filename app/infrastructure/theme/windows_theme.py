"""Native Windows light/dark theme detection + Fusion palette application.

Reads ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize``
and listens for ``WM_SETTINGCHANGE``/``WM_THEMECHANGED`` via a native event
filter so the app follows theme switches live. Exposes a ``theme_changed``
signal object for Qt wiring.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject
from PyQt6.QtGui import QColor, QPalette

from app.domain.entities import LogCategory, LogLevel

logger = logging.getLogger(__name__)

THEME_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A


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
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0x00, 0x78, 0xD4))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0x20, 0x20, 0x20))
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
    return palette


class _ThemeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "WindowsTheme"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message in (WM_SETTINGCHANGE, WM_THEMECHANGED):
                    self._owner._on_native_change()  # noqa: SLF001
            except (ValueError, TypeError, ctypes.ArgumentError):
                pass
        return False


class WindowsTheme(QObject):
    """Owns the theme state and an event-filter bridge; not a Qt signal emitter
    itself (the presentation layer connects via a callback to stay decoupled)."""

    def __init__(self, app, parent: QObject | None = None):
        super().__init__(parent)
        self._app = app
        self._callbacks: list = []
        self._filter = _ThemeEventFilter(self)
        app.installNativeEventFilter(self._filter)

    def install_change_callback(self, callback) -> None:
        """``callback(dark: bool)`` invoked (UI-thread assumed) on theme change."""
        self._callbacks.append(callback)

    def _on_native_change(self) -> None:
        dark = is_windows_dark()
        for callback in self._callbacks:
            try:
                callback(dark)
            except Exception:  # noqa: BLE001
                logger.debug("theme callback error", exc_info=True)

    def apply(self, app, dark: bool) -> None:
        app.setStyle("Fusion")
        app.setPalette(dark_palette() if dark else light_palette())

    def current_is_dark(self) -> bool:
        return is_windows_dark()

    def log_theme(self, logger_adapter, dark: bool) -> None:
        logger_adapter.log(LogCategory.THEME, LogLevel.INFO, f"Theme: {'dark' if dark else 'light'}")
