"""QAbstractTableModel for the daily meter readings table."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.domain.entities import Dashboard, Source, ViewUnit
from app.presentation.i18n import Translator

_COLUMNS = ("date", "import", "interpolated", "modified", "source", "restore")


class MeterTableModel(QAbstractTableModel):
    """Columns: Date, Import, Interpolated, Modified, Source (unit-aware display)."""

    def __init__(self, tr: Translator, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._rows: list[tuple[date, Decimal | None, Decimal | None, Decimal, Source]] = []
        self._dashboard: Dashboard | None = None

    def set_dashboard(self, dashboard: Dashboard) -> None:
        self.beginResetModel()
        self._dashboard = dashboard
        self._rows = dashboard.table_rows if dashboard else []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(_COLUMNS):
            key = {
                "date": "table.date",
                "import": "table.import_value",
                "interpolated": "table.interpolated_value",
                "modified": "table.modified_value",
                "source": "table.source",
                "restore": "table.restore",
            }[_COLUMNS[section]]
            return self._tr.t(key)
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        col = _COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == "date":
                return self._tr.format_date(row[0])
            if col == "source":
                return self._tr.t(f"source.{row[4].value}")
            if col == "restore":
                return ""
            value = {"import": row[1], "interpolated": row[2], "modified": row[3]}[col]
            return self._format(value, row[0])
        if role == Qt.ItemDataRole.TextAlignmentRole and col in ("import", "interpolated", "modified"):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.UserRole:
            return row  # full row for the table view (edit/restore)
        return None

    def _format(self, value: Decimal | None, day: date) -> str:
        if self._dashboard is None or value is None:
            return "–"
        if self._dashboard.unit == ViewUnit.KWH:
            cal, z = self._dashboard.day_factors.get(day, (Decimal("11.342"), Decimal("0.9589")))
            converted = value * cal * z
        else:
            converted = value
        return self._tr.format_number(converted)
