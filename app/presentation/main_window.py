"""Main window - toolbar, menus, global date filter, tabs, log dock, wiring."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDockWidget,
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
from app.presentation.log_panel import LogPanel
from app.presentation.manual_edit_dialog import ManualEditDialog
from app.presentation.meter_table import MeterTableView
from app.presentation.settings_dialog import SettingsDialog
from app.presentation.table_model import MeterTableModel
from app.presentation.update_dialog import UpdateDialog
from app.presentation.workers import SyncWorker, UpdateCheckWorker


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

        self._build_toolbar_and_menus()
        self._build_central()
        self._build_log_dock()

        # controller -> views
        services.controller.dashboard_changed.connect(self._on_dashboard_changed)
        # table interactions
        self._table_view.edit_day.connect(self._open_edit_dialog)
        self._table_view.restore_day.connect(self._restore_day)
        # theme
        services.theme.install_change_callback(self._on_theme_changed)
        self._charts.apply_theme(services.theme.current_is_dark())

        services.controller.refresh()
        self._logger.log(LogCategory.GUI, LogLevel.INFO, "Main window ready")
    # -- construction -----------------------------------------------------------
    def _build_toolbar_and_menus(self) -> None:
        toolbar = QToolBar("main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self._tr.t("menu.download_missing"), self._download_missing)
        toolbar.addAction(self._tr.t("menu.import_archive"), self._import_archive)
        toolbar.addSeparator()
        toolbar.addAction(self._tr.t("menu.settings"), self._open_settings)
        toolbar.addSeparator()
        toolbar.addAction(self._tr.t("menu.check_updates"), self._check_updates)
        toolbar.addSeparator()
        toolbar.addAction(self._tr.t("menu.exit"), self.close)

        file_menu = self.menuBar().addMenu(self._tr.t("menu.file"))
        file_menu.addAction(self._tr.t("menu.download_missing"), self._download_missing)
        file_menu.addAction(self._tr.t("menu.import_archive"), self._import_archive)
        file_menu.addSeparator()
        file_menu.addAction(self._tr.t("menu.settings"), self._open_settings)
        file_menu.addAction(self._tr.t("menu.check_updates"), self._check_updates)
        file_menu.addSeparator()
        language_menu = file_menu.addMenu(self._tr.t("menu.language"))
        for lang, label in (
            ("auto", self._tr.t("settings.lang_auto")),
            ("en", "English"),
            ("de", "Deutsch"),
        ):
            language_menu.addAction(label, lambda _=False, lang=lang: self._change_language(lang))
        file_menu.addAction(self._tr.t("menu.exit"), self.close)

    def _build_central(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        # global date-range filter bar
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel(self._tr.t("charts.from")))
        self._from_edit = QDateEdit(QDate.currentDate().addMonths(-1))
        self._to_edit = QDateEdit(QDate.currentDate())
        for edit in (self._from_edit, self._to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        filter_bar.addWidget(self._from_edit)
        filter_bar.addWidget(QLabel(self._tr.t("charts.to")))
        filter_bar.addWidget(self._to_edit)
        self._preset = QComboBox()
        for key in ("all", "30d", "90d", "year"):
            self._preset.addItem(
                self._tr.t("table.filter_all") if key == "all" else self._tr.t(f"table.filter_{key}"),
                key,
            )
        filter_bar.addWidget(self._preset)
        filter_bar.addStretch(1)
        layout.addLayout(filter_bar)

        self._tabs = QTabWidget(central)
        self._tabs.addTab(self._table_view, self._tr.t("main.tab.table"))
        self._tabs.addTab(self._charts, self._tr.t("main.tab.charts"))
        layout.addWidget(self._tabs)

        self.statusBar().showMessage(self._tr.t("status.ready"))
        self.setCentralWidget(central)

        self._preset.currentIndexChanged.connect(self._apply_preset)
        self._from_edit.dateChanged.connect(self._apply_range)
        self._to_edit.dateChanged.connect(self._apply_range)

    def _build_log_dock(self) -> None:
        self._log_panel = LogPanel(self._tr, self._logger, self)
        dock = QDockWidget(self._tr.t("log.title"), self)
        dock.setWidget(self._log_panel)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    # -- filters -----------------------------------------------------------------
    def _apply_preset(self) -> None:
        self._svc.controller.apply_preset(self._preset.currentData())

    def _apply_range(self) -> None:
        f = self._from_edit.date()
        t = self._to_edit.date()
        self._svc.controller.set_date_range(
            date(f.year(), f.month(), f.day()),
            date(t.year(), t.month(), t.day()),
        )

    # -- controller slots ---------------------------------------------------------
    def _on_dashboard_changed(self, dashboard) -> None:
        self._table_model.set_dashboard(dashboard)
        self._charts.set_dashboard(dashboard)

    # -- table interactions -------------------------------------------------------
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
        dialog = ManualEditDialog(
            self._tr,
            day,
            import_value,
            interpolated_value,
            modified_value,
            source,
            self,
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
        self._svc.restore_use_case.run(day)
        self._svc.controller.refresh()

    # -- actions -------------------------------------------------------------------
    def _download_missing(self) -> None:
        self.statusBar().showMessage(self._tr.t("status.syncing"))
        worker = SyncWorker(self._svc.sync_use_case.run, self)
        worker.finished_result.connect(self._on_sync_finished)
        worker.failed.connect(self._on_sync_failed)
        worker.start()

    def _import_archive(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self._tr.t("msg.choose_files"),
            "",
            "Logfiles (*.csv *.txt);;All files (*)",
        )
        if not paths:
            return
        from pathlib import Path

        files = [Path(p) for p in paths]
        self.statusBar().showMessage(self._tr.t("status.syncing"))
        worker = SyncWorker(lambda: self._svc.archive_import_use_case.run(files), self)
        worker.finished_result.connect(self._on_sync_finished)
        worker.failed.connect(self._on_sync_failed)
        worker.start()

    def _open_settings(self) -> None:
        settings_dict = self._svc.settings_use_case.get_all()
        intervals = self._svc.gas_parameters_use_case.list()
        dialog = SettingsDialog(self._tr, settings_dict, intervals, self)
        if not dialog.exec():
            return
        changes, upserts, deletes = dialog.collect()
        try:
            self._svc.settings_use_case.update(changes)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._tr.t("settings.title"),
                self._tr.t("settings.invalid", errors=str(exc)),
            )
            return
        from app.application.models import ParamsIntervalRequest

        errors: list[str] = []
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
        for valid_from, valid_to in deletes:
            self._svc.gas_parameters_use_case.delete(valid_from, valid_to)
        if errors:
            QMessageBox.warning(
                self,
                self._tr.t("settings.title"),
                self._tr.t("settings.invalid", errors="; ".join(errors[:3])),
            )
        language = changes.get("app.language", "auto")
        self._change_language(language)
        self._svc.controller.refresh()

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
        self.setWindowTitle(self._tr.t("app.title"))
        self._tabs.setTabText(0, self._tr.t("main.tab.table"))
        self._tabs.setTabText(1, self._tr.t("main.tab.charts"))
        self._logger.log(LogCategory.GUI, LogLevel.INFO, f"Language set to {language}")
        self._svc.controller.refresh()

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

    # -- theme ---------------------------------------------------------------------
    def _on_theme_changed(self, dark: bool) -> None:
        self._svc.theme.apply(self._qapplication(), dark)
        self._charts.apply_theme(dark)

    def _apply_theme(self, dark: bool) -> None:
        self._charts.apply_theme(dark)

    @staticmethod
    def _qapplication():
        from PyQt6.QtWidgets import QApplication

        return QApplication.instance()

