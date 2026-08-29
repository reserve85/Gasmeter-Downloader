"""Manual edit dialog - edits ONLY the Modified value (m³)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from app.domain.entities import Source
from app.presentation.i18n import Translator


class ManualEditDialog(QDialog):
    def __init__(
        self,
        tr: Translator,
        day: date,
        import_value: Decimal | None,
        interpolated_value: Decimal | None,
        modified_value: Decimal,
        source: Source,
        parent=None,
    ):
        super().__init__(parent)
        self._tr = tr
        self.setWindowTitle(tr.t("manual.title"))
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow(tr.t("manual.date_label"), QLabel(tr.format_date(day)))
        import_label = QLabel(tr.format_number(import_value) if import_value is not None else "–")
        interpolated_label = QLabel(tr.format_number(interpolated_value) if interpolated_value is not None else "–")
        form.addRow(tr.t("manual.import_label"), import_label)
        form.addRow(tr.t("manual.interpolated_label"), interpolated_label)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 100_000_000.0)
        self._spin.setDecimals(3)
        self._spin.setValue(float(modified_value))
        form.addRow(tr.t("manual.modified_label"), self._spin)
        layout.addLayout(form)

        info = QLabel(tr.t("manual.info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr.t("manual.ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr.t("manual.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> Decimal:
        return Decimal(str(self._spin.value()))
