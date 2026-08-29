"""Update check/apply dialog."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
)
from app.presentation.i18n import Translator


class UpdateDialog(QDialog):
    def __init__(
        self,
        tr: Translator,
        current_version: str,
        check_fn: Callable[[], dict],
        apply_fn: Callable[[str], bool],
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
        try:
            ok = self._apply_fn(url)
        except Exception as exc:  # noqa: BLE001 - dev mode / packaging errors
            self._status.setText(self._tr.t("update.error", error=str(exc)))
            return
        if not ok:
            self._status.setText(self._tr.t("update.error", error="apply failed"))
            return
        self._status.setText(self._tr.t("update.restarted"))
        from PyQt6.QtWidgets import QApplication

        QApplication.quit()
