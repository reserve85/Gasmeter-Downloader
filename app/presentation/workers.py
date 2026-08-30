"""Worker threads for long-running (network) operations."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class SyncWorker(QThread):
    """Runs a blocking callable (sync / archive import) off the UI thread."""

    finished_result = pyqtSignal(object)  # SyncResult
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D102
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished_result.emit(result)


class UpdateCheckWorker(QThread):
    """Runs the update check off the UI thread."""

    finished_result = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D102
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished_result.emit(result)
