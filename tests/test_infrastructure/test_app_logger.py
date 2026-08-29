"""AppLogger tests: in-memory only, zero disk output, history, GUI callback."""

from __future__ import annotations

import logging

from app.domain.entities import LogCategory, LogLevel
from app.infrastructure.logging.app_logger import AppLogger


def test_logs_to_history_no_files(tmp_path):
    logger = AppLogger()
    logger.log(LogCategory.STARTUP, LogLevel.INFO, "hello")
    history = logger.history()
    assert len(history) == 1
    assert "<STARTUP>" in history[0]
    assert "[INFO]" in history[0]
    assert "hello" in history[0]
    # zero disk output
    assert not logger.has_disk_handlers()
    assert list(tmp_path.iterdir()) == []


def test_gui_callback_receives_lines():
    logger = AppLogger()
    received = []
    logger.install_gui_handler(received.append)
    logger.log(LogCategory.DOWNLOAD, LogLevel.INFO, "downloaded")
    assert received and "downloaded" in received[0]


def test_bounded_deque():
    logger = AppLogger(max_lines=3)
    for i in range(10):
        logger.log(LogCategory.DB, LogLevel.DEBUG, f"event {i}")
    history = logger.history()
    assert len(history) == 3
    assert "event 7" in history[0]


def test_clear():
    logger = AppLogger()
    logger.log(LogCategory.GUI, LogLevel.INFO, "x")
    logger.clear()
    assert logger.history() == []


def test_logger_name_is_gasmeter():
    AppLogger()
    assert logging.getLogger("gasmeter").handlers
