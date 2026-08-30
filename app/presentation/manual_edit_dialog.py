"""Manual edit dialog - edits ONLY the Modified value (m³).

The spinbox is restricted to the inclusive range between the previous day's
and the next day's value (the meter is a non-decreasing series). The
ascending-order rule is authoritatively enforced by the use case too.
"""

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

        lower, upper = _allowed_range(prev_value, next_value)
        self._spin = QDoubleSpinBox()
        self._spin.setRange(lower, upper)
        self._spin.setDecimals(3)
        self._spin.setValue(float(modified_value))
        form.addRow(tr.t("manual.modified_label"), self._spin)
        layout.addLayout(form)

        if prev_value is not None or next_value is not None:
            info = QLabel(
                tr.t(
                    "manual.ascending_error",
                    prev=tr.format_number(lower),
                    next=tr.format_number(upper),
                )
            )
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
