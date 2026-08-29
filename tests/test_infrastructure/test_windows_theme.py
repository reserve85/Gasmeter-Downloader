"""Windows theme tests: registry detection (mocked) + palette application smoke.

Windows-only (winreg / wintypes); self-skips on other platforms so the CI gate
stays portable.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only theme")

from app.infrastructure.theme.windows_theme import (  # noqa: E402
    WindowsTheme,
    dark_palette,
    is_windows_dark,
    light_palette,
)


def test_is_windows_dark_reads_registry():
    with mock.patch("winreg.OpenKey", return_value=mock.MagicMock()) as ok:
        with mock.patch("winreg.QueryValueEx", return_value=(0, 1)):
            assert is_windows_dark() is True
            ok.assert_called_once()
    with mock.patch("winreg.OpenKey", return_value=mock.MagicMock()):
        with mock.patch("winreg.QueryValueEx", return_value=(1, 1)):
            assert is_windows_dark() is False


def test_is_windows_dark_defaults_light_on_error():
    with mock.patch("winreg.OpenKey", side_effect=OSError):
        assert is_windows_dark() is False


def test_palette_application_smoke(qapp):
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    theme = WindowsTheme(app)
    theme.apply(app, True)
    assert app.style().objectName().lower() == "fusion"
    assert dark_palette() is not None
    assert light_palette() is not None


def test_change_callback_invoked(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    calls = []
    theme.install_change_callback(lambda dark: calls.append(dark))
    theme._on_native_change()  # noqa: SLF001
    assert calls == [theme.current_is_dark()]
