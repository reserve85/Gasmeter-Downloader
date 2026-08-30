"""QTableView for meter readings with edit/restore actions."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QMenu, QPushButton, QTableView

from app.presentation.table_model import MeterTableModel


class MeterTableView(QTableView):
    """Double-click edits the Modified value; right-click offers Restore."""

    edit_day = pyqtSignal(date)
    restore_day = pyqtSignal(date)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_click)

    def set_model(self, model: MeterTableModel) -> None:
        self.setModel(model)
        model.modelReset.connect(self._refresh_buttons)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.setUpdatesEnabled(False)
        restore_col = self.model().columnCount() - 1
        for row in range(self.model().rowCount()):
            index = self.model().index(row, restore_col)
            button = QPushButton(self._tr.t("table.restore"))
            day = self.model()._rows[row][0]  # noqa: SLF001
            button.clicked.connect(lambda _=False, d=day: self.restore_day.emit(d))
            self.setIndexWidget(index, button)
        self.setUpdatesEnabled(True)

    def _on_double_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = self.model()._rows[index.row()]  # noqa: SLF001
        self.edit_day.emit(row[0])

    def _show_context_menu(self, position) -> None:
        index = self.indexAt(position)
        if not index.isValid():
            return
        row = self.model()._rows[index.row()]  # noqa: SLF001
        menu = QMenu(self)
        menu.addAction(self._tr.t("manual.title"), lambda: self.edit_day.emit(row[0]))
        menu.addSeparator()
        menu.addAction(self._tr.t("table.restore"), lambda: self.restore_day.emit(row[0]))
        menu.exec(self.viewport().mapToGlobal(position))
