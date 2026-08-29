"""Settings dialog - device, storage, language, unit, gas parameters, token."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.presentation.i18n import Translator


def _date_from_edit(edit: QDateEdit) -> date | None:
    qd = edit.date()
    return date(qd.year(), qd.month(), qd.day())


class SettingsDialog(QDialog):
    def __init__(
        self,
        tr: Translator,
        settings_dict: dict,
        intervals: list,
        parent=None,
    ):
        super().__init__(parent)
        self._tr = tr
        self._settings_dict = settings_dict
        self.setWindowTitle(tr.t("settings.title"))
        self._intervals = list(intervals)

        root = QVBoxLayout(self)

        # -- device + app -------------------------------------------------------
        device_group = QGroupBox("", self)
        device_form = QFormLayout(device_group)
        self._ip_edit = QLineEdit(str(settings_dict.get("device.ip", "192.168.10.65")))
        device_form.addRow(tr.t("settings.device_ip"), self._ip_edit)
        self._max_days = QSpinBox()
        self._max_days.setRange(1, 3650)
        self._max_days.setValue(int(settings_dict.get("device.max_download_days", 30)))
        device_form.addRow(tr.t("settings.max_days"), self._max_days)
        self._language = QComboBox()
        self._language.addItem(tr.t("settings.lang_auto"), "auto")
        self._language.addItem("English", "en")
        self._language.addItem("Deutsch", "de")
        index = self._language.findData(str(settings_dict.get("app.language", "auto")))
        self._language.setCurrentIndex(max(index, 0))
        device_form.addRow(tr.t("settings.language"), self._language)
        self._unit = QComboBox()
        self._unit.addItem(tr.t("charts.unit_m3"), "m³")
        self._unit.addItem(tr.t("charts.unit_kwh"), "kWh")
        index = self._unit.findData(str(settings_dict.get("app.unit", "m³")))
        self._unit.setCurrentIndex(max(index, 0))
        device_form.addRow(tr.t("settings.unit"), self._unit)
        root.addWidget(device_group)

        # -- storage ------------------------------------------------------------
        storage_group = QGroupBox(tr.t("settings.paths"), self)
        storage_form = QFormLayout(storage_group)
        self._download_edit = QLineEdit(str(settings_dict.get("paths.download", "")))
        self._archive_edit = QLineEdit(str(settings_dict.get("paths.archive", "")))
        self._db_edit = QLineEdit(str(settings_dict.get("paths.database", "")))
        storage_form.addRow(tr.t("settings.paths.download"), self._path_row(self._download_edit, is_dir=True))
        storage_form.addRow(tr.t("settings.paths.archive"), self._path_row(self._archive_edit, is_dir=True))
        storage_form.addRow(tr.t("settings.paths.database"), self._path_row(self._db_edit, is_dir=False))
        root.addWidget(storage_group)
# -- gas parameters -----------------------------------------------------
        gas_group = QGroupBox(tr.t("settings.gas_header"), self)
        gas_layout = QVBoxLayout(gas_group)
        self._gas_table = QTableWidget(0, 4, self)
        self._gas_table.setHorizontalHeaderLabels(
            [
                tr.t("settings.valid_from"),
                tr.t("settings.valid_to"),
                tr.t("settings.calorific"),
                tr.t("settings.z_value"),
            ]
        )
        self._gas_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        gas_layout.addWidget(self._gas_table)

        edit_row = QHBoxLayout()
        self._from_edit = QDateEdit(QDate.currentDate())
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setDisplayFormat("yyyy-MM-dd")
        self._to_edit = QDateEdit(QDate.currentDate())
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setDisplayFormat("yyyy-MM-dd")
        self._to_open = QCheckBox("∞")
        self._to_open.toggled.connect(self._toggle_open_ended)
        self._cal_spin = QDoubleSpinBox()
        self._cal_spin.setRange(0.0, 100.0)
        self._cal_spin.setDecimals(4)
        self._cal_spin.setValue(float(settings_dict.get("gas.default_calorific", 11.342)))
        self._z_spin = QDoubleSpinBox()
        self._z_spin.setRange(0.0, 10.0)
        self._z_spin.setDecimals(4)
        self._z_spin.setValue(float(settings_dict.get("gas.default_z_value", 0.9589)))
        for label, widget in (
            (tr.t("settings.valid_from"), self._from_edit),
            (tr.t("settings.valid_to"), self._to_edit),
            ("", self._to_open),
            (tr.t("settings.calorific"), self._cal_spin),
            (tr.t("settings.z_value"), self._z_spin),
        ):
            edit_row.addWidget(QLabel(label))
            edit_row.addWidget(widget)
        gas_layout.addLayout(edit_row)

        buttons_row = QHBoxLayout()
        add_button = QPushButton(tr.t("settings.add_interval"))
        add_button.clicked.connect(self._add_interval)
        delete_button = QPushButton(tr.t("settings.delete_interval"))
        delete_button.clicked.connect(self._delete_interval)
        buttons_row.addWidget(add_button)
        buttons_row.addWidget(delete_button)
        gas_layout.addLayout(buttons_row)
        root.addWidget(gas_group)

        # -- token --------------------------------------------------------------
        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText(tr.t("settings.token"))
        root.addWidget(self._path_row(self._token_edit, is_dir=False))

        self._refresh_gas_table()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr.t("settings.ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr.t("settings.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
# -- helpers ----------------------------------------------------------------
    def _path_row(self, edit: QLineEdit, is_dir: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        browse = QPushButton(self._tr.t("settings.browse"))
        browse.clicked.connect(lambda: self._browse(edit, is_dir))
        layout.addWidget(browse)
        return row

    def _browse(self, edit: QLineEdit, is_dir: bool) -> None:
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, self._tr.t("settings.browse"), edit.text())
            if path:
                edit.setText(path)
        else:
            path, _ = QFileDialog.getSaveFileName(self, self._tr.t("settings.browse"), edit.text())
            if path:
                edit.setText(path)

    def _toggle_open_ended(self, checked: bool) -> None:
        self._to_edit.setEnabled(not checked)

    def _refresh_gas_table(self) -> None:
        self._gas_table.setRowCount(0)
        for interval in self._intervals:
            self._append_interval_row(
                interval.valid_from,
                interval.valid_to,
                interval.calorific_value,
                interval.z_value,
            )

    def _append_interval_row(self, from_day: date, to_day: date | None, cal: Decimal, z: Decimal) -> None:
        row = self._gas_table.rowCount()
        self._gas_table.insertRow(row)
        self._gas_table.setItem(row, 0, QTableWidgetItem(from_day.isoformat()))
        self._gas_table.setItem(row, 1, QTableWidgetItem(to_day.isoformat() if to_day else "∞"))
        self._gas_table.setItem(row, 2, QTableWidgetItem(f"{cal:f}"))
        self._gas_table.setItem(row, 3, QTableWidgetItem(f"{z:f}"))

    def _add_interval(self) -> None:
        from_day = _date_from_edit(self._from_edit)
        to_day = None if self._to_open.isChecked() else _date_from_edit(self._to_edit)
        if to_day is not None and to_day < from_day:
            return
        cal = Decimal(str(self._cal_spin.value()))
        z = Decimal(str(self._z_spin.value()))
        self._append_interval_row(from_day, to_day, cal, z)
        self._intervals.append((from_day, to_day, cal, z))

    def _delete_interval(self) -> None:
        row = self._gas_table.currentRow()
        if row < 0 or row >= len(self._intervals):
            return
        self._intervals.pop(row)
        self._gas_table.removeRow(row)

    # -- result ----------------------------------------------------------------
    def collect(self) -> tuple[dict, list, list]:
        """Returns (settings_changes, param_upserts, param_deletes)."""
        changes: dict = {
            "device.ip": self._ip_edit.text().strip(),
            "device.max_download_days": self._max_days.value(),
            "app.language": self._language.currentData(),
            "app.unit": self._unit.currentData(),
            "paths.download": self._download_edit.text().strip(),
            "paths.archive": self._archive_edit.text().strip(),
            "paths.database": self._db_edit.text().strip(),
        }
        token = self._token_edit.text().strip()
        if token:
            changes["update.token"] = token
        return changes, self._intervals, []
