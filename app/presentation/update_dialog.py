"""Update check/apply dialog."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
from app.presentation.i18n import Translator


class UpdateDialog(QDialog):
    def __init__(
        self,
        tr: Translator,
        current_version: str,
        check_fn: Callable[[], dict],
        apply_fn: Callable[..., bool],
        parent=None,
    ):
        super().__init__(parent)
        self._tr = tr
        self._check_fn = check_fn
        self._apply_fn = apply_fn
        self._check_result: dict = {}
        self.setWindowTitle(tr.t("update.title"))

        layout = QVBoxLayout(self)
        self._status = QLabel(tr.t("update.checking"))
        layout.addWidget(self._status)
        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        layout.addWidget(self._notes)

        self._check_button = QPushButton(tr.t("update.check"))
        self._apply_button = QPushButton(tr.t("update.download_apply"))
        self._apply_button.setEnabled(False)
        close_button = QPushButton(tr.t("update.close"))
        self._check_button.clicked.connect(self._run_check)
        self._apply_button.clicked.connect(self._run_apply)
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self._check_button)
        buttons.addWidget(self._apply_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        # auto-check on open
        self._run_check()

    def _run_check(self) -> None:
        self._status.setText(self._tr.t("update.checking"))
        result = self._check_fn()
        self._check_result = result or {}
        if self._check_result.get("error"):
            self._status.setText(self._tr.t("update.error", error=self._check_result["error"]))
        elif self._check_result.get("has_update"):
            self._status.setText(
                self._tr.t("update.available", version=self._check_result.get("latest_version", ""))
            )
            self._apply_button.setEnabled(True)
        else:
            self._status.setText(self._tr.t("update.up_to_date", version=""))
        self._notes.setPlainText(self._check_result.get("release_notes", "") or "")

    def _run_apply(self) -> None:
        url = self._check_result.get("download_url", "")
        if not url:
            return
        # Live download progress (MusicSceneReleaser pattern): github_updater
        # reports (bytes, total) through the callback; processEvents keeps the
        # bar repainting while the blocking transfer runs.
        progress = QProgressDialog(self._tr.t("update.downloading"), None, 0, 100, self)
        progress.setWindowTitle(self._tr.t("update.title"))
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setAutoClose(False)
        progress.show()

        def report(downloaded: int, total: int) -> None:
            if total > 0:
                progress.setValue(int(downloaded * 100 / total))
            QApplication.processEvents()

        try:
            ok = self._apply_fn(url, "", report)
        except Exception as exc:  # noqa: BLE001 - dev mode / packaging errors
            progress.close()
            self._status.setText(self._tr.t("update.error", error=str(exc)))
            return
        progress.setValue(100)
        progress.close()
        if not ok:
            self._status.setText(self._tr.t("update.error", error="apply failed"))
            return
        self._status.setText(self._tr.t("update.restarted"))
        self._apply_button.setEnabled(False)
