"""Manual edit dialog - edits ONLY the Modified value (m³).

The spinbox is restricted to the inclusive range between the previous day's
and the next day's value (the meter is a non-decreasing series). The
ascending-order rule is authoritatively enforced by the use case too.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from app.domain.entities import Source
from app.presentation.i18n import Translator

_MAX_METER = 100_000_000.0


def _allowed_range(prev_value: Decimal | None, next_value: Decimal | None) -> tuple[float, float]:
    """Inclusive ascending-order bounds; None neighbors leave one side open."""
    lower = float(prev_value) if prev_value is not None else 0.0
    upper = float(next_value) if next_value is not None else _MAX_METER
    if lower > upper:  # inconsistent neighbours: never block manual corrections
        lower, upper = 0.0, _MAX_METER
    return lower, upper


class ManualEditDialog(QDialog):
    def __init__(
        self,
        tr: Translator,
        day: date,
        import_value: Decimal | None,
        interpolated_value: Decimal | None,
        modified_value: Decimal,
        source: Source,
        prev_value: Decimal | None = None,
        next_value: Decimal | None = None,
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

        prev_label = QLabel(tr.format_number(prev_value) if prev_value is not None else "–")
        next_label = QLabel(tr.format_number(next_value) if next_value is not None else "–")
        form.addRow(tr.t("manual.prev_value"), prev_label)
        form.addRow(tr.t("manual.next_value"), next_label)

        self._lower, self._upper = _allowed_range(prev_value, next_value)
        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, _MAX_METER)
        self._spin.setDecimals(3)
        self._spin.setMinimumWidth(160)
        self._spin.setValue(float(modified_value))

        self._icon_label = QLabel("")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        spin_row = QHBoxLayout()
        spin_row.addWidget(self._spin)
        spin_row.addWidget(self._icon_label)
        form.addRow(tr.t("manual.modified_label"), spin_row)
        layout.addLayout(form)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText(tr.t("manual.ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr.t("manual.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._spin.valueChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        v = self._spin.value()
        in_range = self._lower <= v <= self._upper
        self._ok_button.setEnabled(in_range)
        if not in_range:
            self._icon_label.setText("✗")
            self._icon_label.setStyleSheet("color: #E53935; font-size: 16px; font-weight: bold;")
            self._status_label.setText(
                self._tr.t(
                    "manual.ascending_error",
                    prev=self._tr.format_number(self._lower),
                    next=self._tr.format_number(self._upper),
                )
            )
        else:
            self._icon_label.setText("✓")
            self._icon_label.setStyleSheet("color: #43A047; font-size: 16px; font-weight: bold;")
            self._status_label.setText("")

    def value(self) -> Decimal:
        return Decimal(str(self._spin.value()))
