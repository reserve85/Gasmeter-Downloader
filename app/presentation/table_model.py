"""QAbstractTableModel for the daily meter readings table."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.domain.entities import Aggregation, Dashboard, Source, ViewUnit
from app.presentation.i18n import Translator

_COLUMNS = ("date", "import", "interpolated", "modified", "source", "daily_m3", "daily_kwh", "restore")


class MeterTableModel(QAbstractTableModel):
    """Columns: Date, Import, Interpolated, Modified, Source, Daily use m³/kWh."""

    def __init__(self, tr: Translator, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._rows: list[tuple[date, Decimal | None, Decimal | None, Decimal, Source]] = []
        self._dashboard: Dashboard | None = None
        self._daily_by_day: dict[date, object] = {}

    def set_dashboard(self, dashboard: Dashboard) -> None:
        self.beginResetModel()
        self._dashboard = dashboard
        self._rows = dashboard.table_rows if dashboard else []
        self._daily_by_day = {
            point.day: point
            for point in dashboard.consumption.get(Aggregation.DAILY, [])
        } if dashboard else {}
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
                "daily_m3": "table.daily_m3",
                "daily_kwh": "table.daily_kwh",
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
            if col in ("daily_m3", "daily_kwh"):
                point = self._daily_by_day.get(row[0])
                if point is None:
                    return "–"
                value = point.volume_m3 if col == "daily_m3" else point.energy_kwh
                return self._tr.format_number(value)
            value = {"import": row[1], "interpolated": row[2], "modified": row[3]}[col]
            return self._format(value, row[0])
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (
            "import", "interpolated", "modified", "daily_m3", "daily_kwh"
        ):
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
