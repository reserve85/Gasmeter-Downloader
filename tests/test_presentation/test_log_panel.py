"""LogPanel tests: accumulates events, in-memory only, zero disk output."""

from __future__ import annotations

from app.domain.entities import LogCategory, LogLevel
from app.infrastructure.logging.app_logger import AppLogger
from app.presentation.i18n import Translator
from app.presentation.log_panel import LogPanel


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
