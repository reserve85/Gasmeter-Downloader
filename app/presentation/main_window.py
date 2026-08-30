"""Main window - toolbar, per-tab filters, tabs (Table/Charts/Log), wiring.

No menu bar: every action lives in the toolbar. The table tab owns daily
From/To pickers (+ presets), the charts tab owns yearly pickers. Both scopes
refresh independently through the DashboardController ("AJAX-like").
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.domain.entities import LogCategory, LogLevel, Source
from app.presentation.charts import ChartsTab
from app.presentation.compare import CompareTab
from app.presentation.log_panel import LogPanel
from app.presentation.manual_edit_dialog import ManualEditDialog
from app.presentation.meter_table import MeterTableView
from app.presentation.settings_dialog import SettingsDialog
from app.presentation.table_model import MeterTableModel
from app.presentation.update_dialog import UpdateDialog
from app.presentation.workers import SyncWorker, UpdateCheckWorker

_TABLE_PRESET_KEYS = (
    ("all", "table.filter_all"),
    ("first_today", "table.filter_first_today"),
    ("30d", "table.filter_30d"),
    ("90d", "table.filter_90d"),
    ("year", "table.filter_year"),
)


class MainWindow(QMainWindow):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._svc = services
        self._tr = services.tr
        self._logger = services.logger

        self.setWindowTitle(self._tr.t("app.title"))
        self.resize(
            int(services.settings.get("window.width", 1100)),
            int(services.settings.get("window.height", 720)),
        )

        self._table_model = MeterTableModel(self._tr, self)
        self._table_view = MeterTableView(self._tr, self)
        self._table_view.set_model(self._table_model)
        self._charts = ChartsTab(self._tr, dark=False, parent=self)
        self._charts.bind(services.controller)

        self._build_toolbar()
        self._build_central()

        # controller -> views (two independent scopes)
        services.controller.table_dashboard_changed.connect(self._on_table_dashboard)
        services.controller.charts_dashboard_changed.connect(self._on_charts_dashboard)
        self._table_view.edit_day.connect(self._open_edit_dialog)
        self._table_view.restore_day.connect(self._restore_day)

        # theme
        services.theme.install_change_callback(self._on_theme_changed)
        self._charts.apply_theme(services.theme.current_is_dark())
        self._compare.apply_theme(services.theme.current_is_dark())
        self._log_panel.set_theme(services.theme.current_is_dark())

        # start the table on "first entry -> today" (owner: default filter), and
        # the charts tab already applied its own "this year" default in ``bind``.
        services.controller.apply_table_preset("first_today")
        self._logger.log(LogCategory.GUI, LogLevel.INFO, "Main window ready")

    def closeEvent(self, event):  # noqa: N802
        """Persist window geometry for the next start."""
        try:
            size = self.size()
            self._svc.settings.set("window.width", size.width())
            self._svc.settings.set("window.height", size.height())
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)

    # -- construction -----------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._action_update_logs = toolbar.addAction(
            self._tr.t("menu.download_missing"), self._update_logfiles
        )
        toolbar.addSeparator()
        self._action_settings = toolbar.addAction(self._tr.t("menu.settings"), self._open_settings)

    # -- central widget --------------------------------------------------------
    def _build_central(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget(central)
        self._tabs.addTab(self._build_table_page(), self._tr.t("main.tab.table"))
        self._tabs.addTab(self._charts, self._tr.t("main.tab.charts"))
        self._compare = CompareTab(
            self._svc.query_use_case, self._svc.settings, self._logger, self._tr, parent=self
        )
        self._compare.bind(self._svc.controller)
        self._tabs.addTab(self._compare, self._tr.t("main.tab.compare"))
        self._log_panel = LogPanel(self._tr, self._logger, parent=self)
        self._tabs.addTab(self._log_panel, self._tr.t("main.tab.log"))
        layout.addWidget(self._tabs)

        self.setCentralWidget(central)
        self.statusBar().showMessage(self._tr.t("status.ready"))

    def _build_table_page(self) -> QWidget:
        page = QWidget(self)
        box = QVBoxLayout(page)

        filter_bar = QHBoxLayout()
        self._from_edit = QDateEdit(QDate.currentDate().addMonths(-1))
        self._to_edit = QDateEdit(QDate.currentDate())
        for edit in (self._from_edit, self._to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self._preset = QComboBox()
        self._preset.addItem(self._tr.t("table.filter_custom"), None)
        for key, label in _TABLE_PRESET_KEYS:
            self._preset.addItem(self._tr.t(label), key)
        self._preset.setCurrentIndex(self._preset.findData("first_today"))

        self._from_label = QLabel(self._tr.t("charts.from"))
        self._to_label = QLabel(self._tr.t("charts.to"))
        filter_bar.addWidget(self._from_label)
        filter_bar.addWidget(self._from_edit)
        filter_bar.addWidget(self._to_label)
        filter_bar.addWidget(self._to_edit)
        filter_bar.addWidget(self._preset)
        filter_bar.addStretch(1)
        box.addLayout(filter_bar)
        box.addWidget(self._table_view, 1)

        self._preset.currentIndexChanged.connect(self._on_table_preset)
        self._from_edit.dateChanged.connect(self._on_table_range)
        self._to_edit.dateChanged.connect(self._on_table_range)
        return page

    # -- table filters ----------------------------------------------------------
    def _on_table_preset(self, index: int) -> None:
        preset = self._preset.itemData(index)
        if preset is None:
            self._apply_picker_range()
            return
        self._svc.controller.apply_table_preset(preset)

    def _on_table_range(self) -> None:
        # a manual date change switches back to an explicit range
        self._preset.blockSignals(True)
        self._preset.setCurrentIndex(self._preset.findData(None))
        self._preset.blockSignals(False)
        self._apply_picker_range()

    def _apply_picker_range(self) -> None:
        start, end = self._from_edit.date(), self._to_edit.date()
        self._svc.controller.set_table_range(
            date(start.year(), start.month(), start.day()),
            date(end.year(), end.month(), end.day()),
        )

    # -- controller slots ---------------------------------------------------------
    def _on_table_dashboard(self, dashboard) -> None:
        self._table_model.set_dashboard(dashboard)
        self._sync_table_pickers()

    def _sync_table_pickers(self) -> None:
        """Mirror the controller's resolved window into the From/To pickers (AJAX).

        Presets must visibly move the date pickers; programmatic updates use
        ``blockSignals`` so no refresh round-trip is triggered. User edits still
        switch the preset to "custom" (see ``_on_table_range``).
        """
        controller = self._svc.controller
        start, end = controller.table_resolved_range()
        preset = controller.table_preset()
        if start is not None and end is not None:
            for edit, day in ((self._from_edit, start), (self._to_edit, end)):
                target = QDate(day.year, day.month, day.day)
                if edit.date() != target:
                    edit.blockSignals(True)
                    edit.setDate(target)
                    edit.blockSignals(False)
        self._preset.blockSignals(True)
        index = self._preset.findData(preset)
        self._preset.setCurrentIndex(index if index >= 0 else self._preset.findData(None))
        self._preset.blockSignals(False)

    def _on_charts_dashboard(self, dashboard) -> None:
        self._charts.set_dashboard(dashboard)

    # -- table interactions ---------------------------------------------------------
    def _open_edit_dialog(self, day: date) -> None:
        reading = self._svc.repo.get_reading(day)
        if reading is None:
            import_value = interpolated_value = None
            modified_value = Decimal("0")
            source = Source.MANUAL
        else:
            import_value = reading.import_value
            interpolated_value = reading.interpolated_value
            modified_value = reading.adjusted_value
            source = reading.source
        prev_reading = self._svc.repo.get_reading(day - timedelta(days=1))
        next_reading = self._svc.repo.get_reading(day + timedelta(days=1))
        dialog = ManualEditDialog(
            self._tr,
            day,
            import_value,
            interpolated_value,
            modified_value,
            source,
            prev_value=prev_reading.adjusted_value if prev_reading else None,
            next_value=next_reading.adjusted_value if next_reading else None,
            parent=self,
        )
        if dialog.exec():
            from app.application.models import ManualEditRequest

            request = ManualEditRequest(day=day, value=dialog.value())
            try:
                self._svc.manual_edit_use_case.run(request)
            except ValueError as exc:
                QMessageBox.warning(self, self._tr.t("manual.title"), str(exc))
                return
            self._svc.controller.refresh()

    def _restore_day(self, day: date) -> None:
        answer = QMessageBox.question(
            self,
            self._tr.t("restore.title"),
            self._tr.t("restore.confirm", day=self._tr.format_date(day)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._svc.restore_use_case.run(day)
        self._svc.controller.refresh()

    # -- actions -----------------------------------------------------------------
    def _update_logfiles(self) -> None:
        """Toolbar action - download every missing logfile (renamed, req.)."""
        self._start_sync(lambda: self._svc.sync_use_case.run())

    def _import_archive(self) -> None:
        """Import ALL logfiles of a selected folder (settings action)."""
        folder = QFileDialog.getExistingDirectory(
            self,
            self._tr.t("msg.choose_folder"),
            "",
        )
        if not folder:
            return
        folder_path = Path(folder)
        files = sorted(
            p for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in (".csv", ".txt")
        )
        if not files:
            self.statusBar().showMessage(self._tr.t("msg.no_files"))
            return
        self._start_sync(lambda: self._svc.archive_import_use_case.run(files))

    def trigger_startup_sync(self) -> None:
        """Start the sync worker (used by the auto-fetch-on-startup option)."""
        self._start_sync(lambda: self._svc.sync_use_case.run())

    def trigger_startup_update_check(self) -> None:
        """Background update check when the app starts (never blocks the UI).

        Runs on a worker thread; pending/errored checks surface in the log and
        status bar only, an available update opens the regular update dialog.
        """
        self.statusBar().showMessage(self._tr.t("status.updating"))
        worker = UpdateCheckWorker(self._svc.check_updates_use_case.run, self)
        worker.finished_result.connect(self._on_startup_update_result)
        worker.failed.connect(
            lambda error: self._logger.log(
                LogCategory.UPDATE, LogLevel.WARNING, f"Startup update check failed: {error}"
            )
        )
        worker.start()

    def _on_startup_update_result(self, result: dict) -> None:
        self.statusBar().showMessage(self._tr.t("status.ready"))
        if not result or result.get("error"):
            reason = (result or {}).get("error", "unknown error")
            self._logger.log(LogCategory.UPDATE, LogLevel.WARNING, f"Startup update check: {reason}")
            return
        if not result.get("has_update"):
            self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Startup update check: up to date")
            return
        version = result.get("latest_version", "")
        self._logger.log(LogCategory.UPDATE, LogLevel.INFO, f"Startup update check: update available ({version})")
        dialog = UpdateDialog(
            self._tr,
            self._svc.version,
            lambda: result,  # already fetched - avoid a second network round-trip
            self._svc.apply_update_use_case.run,
            self,
        )
        dialog.exec()

    def _start_sync(self, fn) -> None:
        self.statusBar().showMessage(self._tr.t("status.syncing"))
        worker = SyncWorker(fn, self)
        worker.finished_result.connect(self._on_sync_finished)
        worker.failed.connect(self._on_sync_failed)
        worker.start()

    def _open_settings(self) -> None:
        settings_dict = self._svc.settings_use_case.get_all()
        intervals = self._svc.gas_parameters_use_case.list()
        dialog = SettingsDialog(
            self._tr,
            settings_dict,
            intervals,
            self,
            theme_mode=str(settings_dict.get("theme.mode", "auto")),
            on_import_archive=self._import_archive,
            on_check_updates=self._check_updates,
        )
        if not dialog.exec():
            return
        changes, upserts, deletes = dialog.collect()
        # Gas parameters are independent of the YAML settings: persist them
        # FIRST so a failing settings-save can never lose edited cal/z values.
        from app.application.models import ParamsIntervalRequest

        errors: list[str] = []
        for valid_from, valid_to in deletes:
            self._svc.gas_parameters_use_case.delete(valid_from, valid_to)
        for upsert in upserts:
            try:
                self._svc.gas_parameters_use_case.upsert(
                    ParamsIntervalRequest(
                        valid_from=upsert[0],
                        valid_to=upsert[1],
                        calorific_value=upsert[2],
                        z_value=upsert[3],
                    )
                )
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            QMessageBox.warning(
                self,
                self._tr.t("settings.title"),
                self._tr.t("settings.invalid", errors="; ".join(errors[:3])),
            )
        old_db_path = str(self._svc.settings.get("paths.database"))
        settings_saved = True
        try:
            self._svc.settings_use_case.update(changes)
        except (ValueError, OSError) as exc:
            settings_saved = False
            # a locked/unwritable config file must not crash the save; surface it
            QMessageBox.warning(
                self,
                self._tr.t("settings.title"),
                self._tr.t("settings.invalid", errors=str(exc)),
            )
        language = changes.get("app.language", "auto")
        self._change_language(language)
        theme_mode = changes.get("theme.mode")
        if theme_mode:
            # persisted via settings_use_case.update above; apply live now
            self._svc.theme.set_mode(theme_mode)
        self._apply_live_device_settings(changes)
        if settings_saved and changes.get("paths.database"):
            new_db_path = str(Path(changes["paths.database"]).resolve())
            if old_db_path != new_db_path:
                QMessageBox.information(
                    self,
                    self._tr.t("settings.title"),
                    self._tr.t("settings.database_restart_required"),
                )
        self._svc.controller.refresh()

    def _apply_live_device_settings(self, changes: dict) -> None:
        """Re-point I/O adapters so device/archive changes work without restart."""
        ip = changes.get("device.ip")
        if ip:
            from app.infrastructure.sources.http_logfile_client import HttpLogfileClient

            self._svc.sync_use_case.set_source(HttpLogfileClient(str(ip)))
        archive = changes.get("paths.archive")
        if archive and getattr(self._svc, "archiver", None) is not None:
            from pathlib import Path

            self._svc.archiver.set_archive_dir(Path(str(archive)))

    def _check_updates(self) -> None:
        self.statusBar().showMessage(self._tr.t("status.updating"))
        worker = UpdateCheckWorker(self._svc.check_updates_use_case.run, self)
        worker.finished_result.connect(self._on_update_result)
        worker.failed.connect(lambda error: self.statusBar().showMessage(error))
        worker.start()

    def _on_update_result(self, result: dict) -> None:
        dialog = UpdateDialog(
            self._tr,
            self._svc.version,
            lambda: result,
            self._svc.apply_update_use_case.run,
            self,
        )
        dialog.exec()

    def _change_language(self, language: str) -> None:
        if language == "auto":
            from app.main import _windows_primary_language

            language = "de" if _windows_primary_language() == 7 else "en"
        self._tr.set_language(language)
        self._svc.settings.set("app.language", language)
        self._retranslate_ui()
        self._logger.log(LogCategory.GUI, LogLevel.INFO, f"Language set to {language}")
        self._svc.controller.refresh()

    def _retranslate_ui(self) -> None:
        """Re-translate all static widget labels (AJAX language switch)."""
        self.setWindowTitle(self._tr.t("app.title"))
        self._tabs.setTabText(0, self._tr.t("main.tab.table"))
        self._tabs.setTabText(1, self._tr.t("main.tab.charts"))
        self._tabs.setTabText(2, self._tr.t("main.tab.compare"))
        self._tabs.setTabText(3, self._tr.t("main.tab.log"))

        self._action_update_logs.setText(self._tr.t("menu.download_missing"))
        self._action_settings.setText(self._tr.t("menu.settings"))

        self._from_label.setText(self._tr.t("charts.from"))
        self._to_label.setText(self._tr.t("charts.to"))
        self._repopulate_table_preset_combo()

        self._charts.apply_language()
        self._compare.retranslate()
        self._log_panel.retranslate()
        self.statusBar().showMessage(self._tr.t("status.ready"))

    def _repopulate_table_preset_combo(self) -> None:
        current = self._preset.currentData()
        self._preset.blockSignals(True)
        self._preset.clear()
        self._preset.addItem(self._tr.t("table.filter_custom"), None)
        for key, label in _TABLE_PRESET_KEYS:
            self._preset.addItem(self._tr.t(label), key)
        index = self._preset.findData(current)
        self._preset.setCurrentIndex(index if index >= 0 else 0)
        self._preset.blockSignals(False)

    # -- sync handlers -----------------------------------------------------------
    def _on_sync_finished(self, result) -> None:
        self.statusBar().showMessage(
            self._tr.t(
                "status.synced",
                downloaded=len(result.downloaded),
                missing=len(result.missing_on_device),
                failed=len(result.failed),
            )
        )
        self._svc.controller.refresh()

    def _on_sync_failed(self, error: str) -> None:
        self.statusBar().showMessage(self._tr.t("msg.sync_failed", error=error))
        self._logger.log(LogCategory.ERROR, LogLevel.ERROR, f"Sync failed: {error}")

    # -- theme -------------------------------------------------------------------
    def _on_theme_changed(self, dark: bool) -> None:
        self._svc.theme.apply(self._qapplication(), dark)
        self._charts.apply_theme(dark)
        self._compare.apply_theme(dark)
        self._log_panel.set_theme(dark)

    @staticmethod
    def _qapplication():
        from PyQt6.QtWidgets import QApplication

        return QApplication.instance()
