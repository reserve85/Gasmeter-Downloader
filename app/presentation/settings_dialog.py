"""Settings dialog - device, storage, language, unit, gas parameters, token."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
        theme_mode: str = "auto",
        on_import_archive=None,
        on_check_updates=None,
    ):
        super().__init__(parent)
        self._tr = tr
        self._settings_dict = settings_dict
        self.setWindowTitle(tr.t("settings.title"))
        self._rows: list[tuple[date, date | None, Decimal, Decimal]] = [
            (i.valid_from, i.valid_to, i.calorific_value, i.z_value)
            for i in intervals
        ]
        self._original_rows: list[tuple[date, date | None, Decimal, Decimal]] = list(self._rows)
        self._editing_index: int | None = None

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
        self._auto_fetch = QCheckBox(tr.t("settings.auto_fetch"))
        self._auto_fetch.setChecked(bool(settings_dict.get("device.auto_fetch_on_startup", False)))
        device_form.addRow("", self._auto_fetch)
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
        self._theme = QComboBox()
        for mode, key in (("auto", "theme.auto"), ("dark", "theme.dark"), ("light", "theme.light")):
            self._theme.addItem(tr.t(key), mode)
        index = self._theme.findData(theme_mode)
        self._theme.setCurrentIndex(max(index, 0))
        device_form.addRow(tr.t("theme.title"), self._theme)
        root.addWidget(device_group)

        # -- actions (folders/update, moved from the toolbar) ---------------------
        if on_import_archive is not None or on_check_updates is not None:
            actions_group = QGroupBox(tr.t("settings.actions_title"), self)
            actions_layout = QVBoxLayout(actions_group)
            if on_import_archive is not None:
                import_button = QPushButton(tr.t("menu.import_archive"))
                import_button.clicked.connect(on_import_archive)
                actions_layout.addWidget(import_button)
            if on_check_updates is not None:
                update_button = QPushButton(tr.t("menu.check_updates"))
                update_button.clicked.connect(on_check_updates)
                actions_layout.addWidget(update_button)
            root.addWidget(actions_group)

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
        self._gas_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._gas_table.setHorizontalHeaderLabels(
            [
                tr.t("settings.valid_from"),
                tr.t("settings.valid_to"),
                tr.t("settings.calorific"),
                tr.t("settings.z_value"),
            ]
        )
        self._gas_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._gas_table.cellDoubleClicked.connect(lambda *_: self._on_edit_interval())
        self._gas_table.currentCellChanged.connect(
            lambda _row, _col, _prev_row, _prev_col: self._on_row_selected()
        )
        gas_layout.addWidget(self._gas_table)

        edit_row = QHBoxLayout()
        self._from_edit = QDateEdit(QDate.currentDate())
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setDisplayFormat("yyyy-MM-dd")
        self._to_edit = QDateEdit(QDate.currentDate())
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setDisplayFormat("yyyy-MM-dd")
        if self._rows:
            # seamless transition: pre-fill with the day after a bounded last interval
            last_to = self._rows[-1][1]
            if last_to is not None:
                next_day = last_to + timedelta(days=1)
                prefill = QDate(next_day.year, next_day.month, next_day.day)
                self._from_edit.setDate(prefill)
                self._to_edit.setDate(prefill)
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
        self._add_button = QPushButton(tr.t("settings.add_interval"))
        self._add_button.clicked.connect(self._add_interval)
        self._edit_button = QPushButton(tr.t("settings.edit_interval"))
        self._edit_button.clicked.connect(self._on_edit_interval)
        self._delete_button = QPushButton(tr.t("settings.delete_interval"))
        self._delete_button.clicked.connect(self._delete_interval)
        buttons_row.addWidget(self._add_button)
        buttons_row.addWidget(self._edit_button)
        buttons_row.addWidget(self._delete_button)
        gas_layout.addLayout(buttons_row)
        root.addWidget(gas_group)

        # -- token --------------------------------------------------------------
        # Plain line edit on purpose: the GitHub token is a string, not a path,
        # so it must NOT carry the path-rows' Browse… button.
        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText(tr.t("settings.token"))
        root.addWidget(self._token_edit)

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
        for (from_day, to_day, cal, z) in self._rows:
            self._append_interval_row(from_day, to_day, cal, z)

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
        if self._editing_index is not None:
            # EDIT: replace the selected row in place (same or new dates).
            self._rows[self._editing_index] = (from_day, to_day, cal, z)
            self._editing_index = None
            self._add_button.setText(self._tr.t("settings.add_interval"))
        else:
            # auto-close every predecessor spanning ``from_day`` (seamless transition)
            for index, (valid_from, valid_to, prev_cal, prev_z) in enumerate(self._rows):
                if valid_from < from_day and (valid_to is None or valid_to >= from_day):
                    self._rows[index] = (valid_from, from_day - timedelta(days=1), prev_cal, prev_z)
            self._rows.append((from_day, to_day, cal, z))
        self._refresh_gas_table()

    def _on_edit_interval(self) -> None:
        row = self._gas_table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        self._editing_index = row
        valid_from, valid_to, cal, z = self._rows[row]
        self._from_edit.setDate(QDate(valid_from.year, valid_from.month, valid_from.day))
        open_ended = valid_to is None
        self._to_open.setChecked(open_ended)
        if not open_ended:
            self._to_edit.setDate(QDate(valid_to.year, valid_to.month, valid_to.day))
        self._cal_spin.setValue(float(cal))
        self._z_spin.setValue(float(z))

    def _on_row_selected(self) -> None:
        """Highlighting a row loads it into the form so edits apply in place.

        This makes "select row -> change Brennwert/Z -> OK" work even without
        pressing the Add/Edit button: the pending edit is committed in
        ``collect``.
        """
        if self._gas_table.currentRow() >= 0:
            self._on_edit_interval()
        else:
            self._editing_index = None

    def _delete_interval(self) -> None:
        row = self._gas_table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        self._rows.pop(row)
        self._gas_table.removeRow(row)
        # the armed form edit referred to the deleted row - never flush it into
        # whatever row shifts into its place.
        self._editing_index = None

    def _flush_pending_edit(self) -> None:
        """Write the currently armed form edit into ``self._rows`` (OK-save)."""
        if self._editing_index is None:
            return
        from_day = _date_from_edit(self._from_edit)
        to_day = None if self._to_open.isChecked() else _date_from_edit(self._to_edit)
        if to_day is not None and to_day < from_day:
            # invalid dates -> leave the row untouched; the settings change is
            # still collected below but the malformed edit is not applied.
            self._editing_index = None
            return
        self._rows[self._editing_index] = (
            from_day,
            to_day,
            Decimal(str(self._cal_spin.value())),
            Decimal(str(self._z_spin.value())),
        )
        self._editing_index = None

    # -- result ----------------------------------------------------------------
    def collect(self) -> tuple[dict, list, list]:
        """Returns (settings_changes, param_row_upserts, param_deletes).

        Any edit still loaded in the form (row selected, values changed) is
        committed first so "change Brennwert/Z and press OK" persists.
        ``param_deletes`` is a list of ``(valid_from, valid_to)`` pairs for
        intervals that existed in the database when the dialog opened but were
        removed by the user.
        """
        self._flush_pending_edit()
        changes: dict = {
            "device.ip": self._ip_edit.text().strip(),
            "device.max_download_days": self._max_days.value(),
            "device.auto_fetch_on_startup": self._auto_fetch.isChecked(),
            "app.language": self._language.currentData(),
            "app.unit": self._unit.currentData(),
            "theme.mode": self._theme.currentData(),
            "paths.download": self._download_edit.text().strip(),
            "paths.archive": self._archive_edit.text().strip(),
            "paths.database": self._db_edit.text().strip(),
        }
        token = self._token_edit.text().strip()
        if token:
            changes["update.token"] = token
        current_keys = {(vf, vt) for (vf, vt, _cal, _z) in self._rows}
        deletes = [
            (vf, vt) for (vf, vt, _cal, _z) in self._original_rows
            if (vf, vt) not in current_keys
        ]
        return changes, list(self._rows), deletes
