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


def test_apply_repolishes_existing_widgets(qapp):
    """Theme switch must visibly update already-created widgets (owner: AJAX)."""
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

    app = QApplication.instance()
    label = QLabel("x")
    label.show()
    button = QPushButton("Save")
    button.show()
    app.processEvents()
    theme = WindowsTheme(app)
    theme.apply(app, True)
    app.processEvents()
    assert label.palette().text().color().name() == dark_palette().text().color().name()
    # children of a repolished top-level must get the new palette too (table/toolbar buttons)
    assert button.palette().buttonText().color().name() == dark_palette().buttonText().color().name()
    theme.apply(app, False)
    app.processEvents()
    assert label.palette().text().color().name() == light_palette().text().color().name()
    assert button.palette().buttonText().color().name() == light_palette().buttonText().color().name()
    label.close()
    button.close()


def test_change_callback_invoked(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    calls = []
    theme.install_change_callback(lambda dark: calls.append(dark))
    # force a "different" theme state so the poll er events
    theme._current_dark = not theme.current_is_dark()  # noqa: SLF001
    theme._poll()  # noqa: SLF001
    assert calls and calls[-1] == theme._current_dark  # noqa: SLF001


def test_set_mode_forces_dark(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    theme.set_mode("dark")
    assert theme.current_is_dark() is True


def test_set_mode_forces_light(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    theme.set_mode("light")
    assert theme.current_is_dark() is False


def test_set_mode_auto_follows_registry(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    theme.set_mode("auto")
    with mock.patch("winreg.OpenKey", return_value=mock.MagicMock()):
        with mock.patch("winreg.QueryValueEx", return_value=(0, 1)):  # dark OS
            assert theme.current_is_dark() is True
        with mock.patch("winreg.QueryValueEx", return_value=(1, 1)):  # light OS
            assert theme.current_is_dark() is False


def test_set_mode_rejects_unknown(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    with pytest.raises(ValueError):
        theme.set_mode("sepia")


def test_set_mode_fires_callbacks_only_on_change(qapp):
    from PyQt6.QtWidgets import QApplication

    theme = WindowsTheme(QApplication.instance())
    calls = []
    theme.install_change_callback(lambda dark: calls.append(dark))
    theme.set_mode("dark")
    theme.set_mode("dark")  # same state -> no new callback
    theme.set_mode("light")
    assert calls == [True, False]
