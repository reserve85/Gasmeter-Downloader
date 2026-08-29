"""In-memory UI log panel - user feed, never written to disk."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from app.presentation.i18n import Translator

_LEVEL_COLORS = {
    "CRITICAL": QColor("#B00020"),
    "ERROR": QColor("#B00020"),
    "WARNING": QColor("#D2691E"),
    "INFO": QColor("#1E1E1E"),
    "DEBUG": QColor("#8A8A8A"),
}


class _SignalBridge(QObject):
    line = pyqtSignal(str)


class LogPanel(QWidget):
    """A bounded, event-driven log viewer fed by the in-memory logger sink.

    Events may arrive from worker threads; the bridge signal marshals them to
    the UI thread via Qt's queued connection.
    """

    def __init__(self, tr: Translator, logger_adapter, parent: QWidget | None = None):
        super().__init__(parent)
        self._tr = tr
        self._bridge = _SignalBridge(self)
        self._bridge.line.connect(self._append_line)
        logger_adapter.install_gui_handler(self._bridge.line.emit)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(self._tr.t("log.title")))
        header.addStretch(1)
        clear_button = QPushButton(self._tr.t("log.clear"))
        clear_button.clicked.connect(lambda: self._clear())
        header.addWidget(clear_button)
        layout.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        layout.addWidget(self._text)

    def _append_line(self, line: str) -> None:
        color = _LEVEL_COLORS.get(_extract_level(line), _LEVEL_COLORS["INFO"])
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        self._text.mergeCurrentCharFormat(fmt)
        self._text.appendPlainText(line)
        self._text.moveCursor(QTextCursor.MoveOperation.End)

    def _clear(self) -> None:
        self._text.clear()

    def plain_text(self) -> str:
        return self._text.toPlainText()


def _extract_level(line: str) -> str:
    for token in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        if f"[{token}]" in line:
            return token
    return "INFO"
