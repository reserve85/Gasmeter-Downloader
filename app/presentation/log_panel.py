"""In-memory UI log panel - user feed, never written to disk, theme-aware."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from app.presentation.i18n import Translator

# Text colors chosen so INFO always contrasts with the widget background in
# both themes (light base #FFFFFF, dark base #1E1E1E).
_LIGHT_LEVEL_COLORS = {
    "CRITICAL": QColor("#B00020"),
    "ERROR": QColor("#B00020"),
    "WARNING": QColor("#B36B00"),
    "INFO": QColor("#1E1E1E"),
    "DEBUG": QColor("#6E6E6E"),
}

_DARK_LEVEL_COLORS = {
    "CRITICAL": QColor("#FF6B6B"),
    "ERROR": QColor("#FF6B6B"),
    "WARNING": QColor("#F5A623"),
    "INFO": QColor("#D6D6D6"),
    "DEBUG": QColor("#8A8A8A"),
}


class _SignalBridge(QObject):
    line = pyqtSignal(str)


class LogPanel(QWidget):
    """A bounded, event-driven log viewer fed by the in-memory logger sink.

    Events may arrive from worker threads; the bridge signal marshals them to
    the UI thread via Qt's queued connection. Lines are buffered so a theme
    switch can re-render every message with the matching palette.
    """

    def __init__(
        self,
        tr: Translator,
        logger_adapter,
        dark: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._tr = tr
        self._dark = dark
        self._colors = _DARK_LEVEL_COLORS if dark else _LIGHT_LEVEL_COLORS
        self._buffer: deque[tuple[str, str]] = deque(maxlen=2000)
        self._bridge = _SignalBridge(self)
        self._bridge.line.connect(self._append_line)
        logger_adapter.install_gui_handler(self._bridge.line.emit)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self._title_label = QLabel(self._tr.t("log.title"))
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._clear_button = QPushButton(self._tr.t("log.clear"))
        self._clear_button.clicked.connect(lambda: self._clear())
        header.addWidget(self._clear_button)
        layout.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        layout.addWidget(self._text)

    def retranslate(self) -> None:
        """Re-translate static labels after a language change."""
        self._title_label.setText(self._tr.t("log.title"))
        self._clear_button.setText(self._tr.t("log.clear"))

    def set_theme(self, dark: bool) -> None:
        """Re-render the buffered lines with the palette matching ``dark``."""
        if self._dark == dark:
            return
        self._dark = dark
        self._colors = _DARK_LEVEL_COLORS if dark else _LIGHT_LEVEL_COLORS
        lines = list(self._buffer)
        self._buffer.clear()
        self._text.clear()
        for level, line in lines:
            self._render_line(level, line)

    def _append_line(self, line: str) -> None:
        level = _extract_level(line)
        self._buffer.append((level, line))
        self._render_line(level, line)
        self._text.moveCursor(QTextCursor.MoveOperation.End)

    def _render_line(self, level: str, line: str) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(self._colors.get(level, self._colors["INFO"]))
        self._text.mergeCurrentCharFormat(fmt)
        self._text.appendPlainText(line)

    def _clear(self) -> None:
        self._buffer.clear()
        self._text.clear()

    def plain_text(self) -> str:
        return self._text.toPlainText()


def _extract_level(line: str) -> str:
    for token in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        if f"[{token}]" in line:
            return token
    return "INFO"
