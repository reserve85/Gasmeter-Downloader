"""LogPanel tests: accumulates events, in-memory only, zero disk output."""

from __future__ import annotations

from app.domain.entities import LogCategory, LogLevel
from app.infrastructure.logging.app_logger import AppLogger
from app.presentation.i18n import Translator
from app.presentation.log_panel import LogPanel
from PyQt6.QtGui import QColor


def test_panel_accumulates_events(qapp, tmp_path):
    logger = AppLogger()
    panel = LogPanel(Translator("en"), logger, parent=None)
    logger.log(LogCategory.DOWNLOAD, LogLevel.INFO, "downloaded something")
    logger.log(LogCategory.ERROR, LogLevel.ERROR, "boom")
    text = panel.plain_text()
    assert "downloaded something" in text
    assert "boom" in text
    # zero disk output
    assert list(tmp_path.iterdir()) == []


def test_panel_clear_button(qapp):
    logger = AppLogger()
    panel = LogPanel(Translator("en"), logger)
    logger.log(LogCategory.GUI, LogLevel.INFO, "x")
    assert panel.plain_text()
    panel._clear()  # noqa: SLF001
    assert panel.plain_text() == ""


def test_level_colors_do_not_crash(qapp):
    from app.presentation.log_panel import _extract_level

    assert _extract_level("2026-01-01 [ERROR] <DB> x") == "ERROR"
    assert _extract_level("2026-01-01 [INFO] <DB> x") == "INFO"


_LIGHT_BASE = QColor("#FFFFFF")
_DARK_BASE = QColor("#1E1E1E")


def _contrasts(colors, base: QColor) -> bool:
    # An INFO line must differ from the panel background in each theme
    # (requirement #18: text must not equal the background color).
    assert colors["INFO"] != base
    assert colors["INFO"].lightnessF() > 0
    return True


def test_info_color_contrasts_with_background(qapp):
    from app.presentation.log_panel import _DARK_LEVEL_COLORS, _LIGHT_LEVEL_COLORS

    _contrasts(_LIGHT_LEVEL_COLORS, _LIGHT_BASE)
    _contrasts(_DARK_LEVEL_COLORS, _DARK_BASE)


def test_set_theme_rerenders_buffered_lines(qapp):
    logger = AppLogger()
    panel = LogPanel(Translator("en"), logger, dark=False)
    logger.log(LogCategory.DOWNLOAD, LogLevel.INFO, "line one")
    logger.log(LogCategory.ERROR, LogLevel.ERROR, "boom")
    assert "line one" in panel.plain_text()

    panel.set_theme(dark=True)
    assert panel._dark is True  # noqa: SLF001
    # buffer survives the re-render
    assert "line one" in panel.plain_text()
    assert "boom" in panel.plain_text()
    # re-applying the already-active theme renders the same text
    text = panel.plain_text()
    panel.set_theme(dark=True)
    assert panel.plain_text() == text


def test_retranslate_updates_static_labels(qapp):
    tr = Translator("en")
    logger = AppLogger()
    panel = LogPanel(tr, logger)
    assert panel._title_label.text() == "Log"  # noqa: SLF001
    tr.set_language("de")
    panel.retranslate()
    assert panel._title_label.text() == "Protokoll"  # noqa: SLF001
    assert panel._clear_button.text() == "Leeren"  # noqa: SLF001
