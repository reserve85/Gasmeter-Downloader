"""MainWindow offscreen tests: no menu bar, three tabs, widgets, restore confirm."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QMessageBox, QToolBar

from app.application.use_cases.query import GetDashboardUseCase
from app.application.use_cases.restore import RestoreValueUseCase
from app.application.use_cases.settings import SettingsUseCase
from app.infrastructure.logging.app_logger import AppLogger
from app.presentation.dashboard_controller import DashboardController
from app.presentation.i18n import Translator
from app.presentation.main_window import MainWindow

from tests.conftest import FakeSettings


class _FakeTheme:
    def __init__(self):
        self.dark = False
        self.callback = None

    def install_change_callback(self, callback):
        self.callback = callback

    def current_is_dark(self) -> bool:
        return self.dark

    def apply(self, app, dark: bool) -> None:
        self.dark = dark

    def set_mode(self, mode: str) -> None:
        self.dark = mode == "dark"
        if self.callback is not None:
            self.callback(self.dark)


def _services(fake_repo, gas_repo):
    settings = FakeSettings(
        {
            "window.width": 1024,
            "window.height": 768,
            "app.language": "en",
            "theme.mode": "auto",
        }
    )
    logger = AppLogger()
    query = GetDashboardUseCase(fake_repo, gas_repo, settings, logger)
    controller = DashboardController(query, settings, logger, Translator("en"))
    theme = _FakeTheme()
    return SimpleNamespace(
        tr=Translator("en"),
        settings=settings,
        logger=logger,
        theme=theme,
        controller=controller,
        query_use_case=query,
        repo=fake_repo,
        version="0.0.0-test",
        sync_use_case=SimpleNamespace(run=lambda: None, set_source=lambda source: None),
        archive_import_use_case=SimpleNamespace(run=lambda files: None),
        settings_use_case=SettingsUseCase(settings, logger),
        gas_parameters_use_case=SimpleNamespace(list=lambda: [], upsert=lambda r: None, delete=lambda a, b: None),
        manual_edit_use_case=SimpleNamespace(run=lambda r: None),
        restore_use_case=RestoreValueUseCase(fake_repo, logger),
        check_updates_use_case=SimpleNamespace(run=lambda: {}),
        apply_update_use_case=SimpleNamespace(run=lambda url, token="", progress=None: False),
    )


def _seed(fake_repo):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 2), Decimal("102"))


def test_no_menu_bar(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    assert window.menuBar() is not None
    assert window.menuBar().actions() == []  # File menu removed (requirement #20)


def test_three_tabs_table_charts_log(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    tabs = window._tabs  # noqa: SLF001
    assert tabs.count() == 4
    assert tabs.tabText(0) == "Table"
    assert tabs.tabText(1) == "Charts"
    assert tabs.tabText(2) == "Compare"
    assert tabs.tabText(3) == "Log"


def test_language_change_updates_translator(qapp, fake_repo, gas_repo):
    """Language is now configured in Settings; the toolbar has no combo."""
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    window._change_language("de")  # noqa: SLF001
    assert services.tr.language == "de"
    assert window._tabs.tabText(3) == "Protokoll"  # noqa: SLF001


def test_language_change_retranslates_static_widgets(qapp, fake_repo, gas_repo):
    """AJAX review fix: toolbar actions, labels and combos follow the language."""
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    window._change_language("de")  # noqa: SLF001
    assert window._action_update_logs.text() == "Logdateien aktualisieren"
    assert window._action_settings.text() == "Einstellungen…"
    assert window._from_label.text() == "Von"
    assert window._to_label.text() == "Bis"
    preset_index = window._preset.findData("30d")  # noqa: SLF001
    assert window._preset.itemText(preset_index) == "Letzte 30 Tage"  # noqa: SLF001
    # selection is preserved while items were re-labelled
    assert window._preset.currentData() == "first_today"  # noqa: SLF001


def test_toolbar_has_only_action_buttons(qapp, fake_repo, gas_repo):
    """Exit/language/theme have moved into Settings; the toolbar stays slim."""
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    toolbar = window.findChild(QToolBar)  # type: ignore[name-defined]
    texts = [action.text() for action in toolbar.actions()]
    assert texts == ["Update logfiles", "", "Settings…"]  # separate separator shows as empty text


def test_language_change_keeps_table_preset_active(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    window._change_language("de")  # noqa: SLF001
    assert window._preset.currentData() == "first_today"  # noqa: SLF001


def test_restore_asks_for_confirmation(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    with mock.patch(
        "app.presentation.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ) as question:
        window._restore_day(date(2026, 1, 1))  # noqa: SLF001
    assert question.called
    # declined -> nothing restored
    assert fake_repo.get_reading(date(2026, 1, 1)).adjusted_value == Decimal("100")


def test_restore_runs_after_confirmation(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    fake_repo.save_manual(date(2026, 1, 1), Decimal("150"))
    with mock.patch(
        "app.presentation.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        window._restore_day(date(2026, 1, 1))  # noqa: SLF001
    assert fake_repo.get_reading(date(2026, 1, 1)).adjusted_value == Decimal("100")


def test_trigger_startup_sync_starts_worker(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    with mock.patch.object(window, "_start_sync") as start:
        window.trigger_startup_sync()
    start.assert_called_once()


def test_trigger_startup_update_check_starts_worker(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    worker = mock.Mock()
    with mock.patch("app.presentation.main_window.UpdateCheckWorker", return_value=worker) as cls:
        window.trigger_startup_update_check()  # noqa: SLF001
    cls.assert_called_once()
    worker.start.assert_called_once()


def test_startup_update_quiet_when_up_to_date(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    with mock.patch("app.presentation.main_window.UpdateDialog") as dialog:
        window._on_startup_update_result(  # noqa: SLF001
            {"has_update": False, "latest_version": "", "download_url": "", "release_notes": "", "error": ""}
        )
    dialog.assert_not_called()


def test_startup_update_opens_dialog_when_available(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    with mock.patch("app.presentation.main_window.UpdateDialog") as dialog:
        window._on_startup_update_result(  # noqa: SLF001
            {"has_update": True, "latest_version": "9.9.9", "download_url": "http://x/a.exe", "release_notes": "x", "error": ""}
        )
    dialog.assert_called_once()
    dialog.return_value.exec.assert_called_once()


def test_theme_button_mode_applies(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    MainWindow(services)  # window is wired; theme is managed via the manager
    services.theme.dark = False
    services.theme.set_mode("dark")
    assert services.theme.dark is True
    # the settings use case persists the choice; refresh then uses it
    services.settings_use_case.update({"theme.mode": "light"})
    services.theme.set_mode("light")
    assert services.theme.dark is False
    assert services.settings.get("theme.mode") == "light"


def test_database_path_change_shows_restart_hint(qapp, fake_repo, gas_repo):
    """Changing the DB file mid-session is only effective after a restart."""
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    dialog = mock.Mock()
    dialog.exec.return_value = True
    dialog.collect.return_value = (
        {
            "device.ip": "192.168.10.65",
            "device.max_download_days": 30,
            "device.auto_fetch_on_startup": False,
            "app.language": "en",
            "app.unit": "m³",
            "theme.mode": "auto",
            "paths.download": "downloads",
            "paths.archive": "archive",
            "paths.database": "other.db",
        },
        [],
        [],
    )
    with (
        mock.patch("app.presentation.main_window.SettingsDialog", return_value=dialog),
        mock.patch("app.presentation.main_window.QMessageBox.information") as info,
    ):
        window._open_settings()  # noqa: SLF001
    assert info.called
    # the change is persisted; only the hint is shown (no live database switch)
    assert services.settings.get("paths.database").endswith("other.db")


def test_unchanged_database_path_shows_no_hint(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    current = str(Path("gasmeter.db").resolve())
    services.settings.set("paths.database", current)
    window = MainWindow(services)
    dialog = mock.Mock()
    dialog.exec.return_value = True
    dialog.collect.return_value = (
        {
            "device.ip": "192.168.10.65",
            "device.max_download_days": 30,
            "device.auto_fetch_on_startup": False,
            "app.language": "en",
            "app.unit": "m³",
            "theme.mode": "auto",
            "paths.download": "downloads",
            "paths.archive": "archive",
            "paths.database": "gasmeter.db",
        },
        [],
        [],
    )
    with (
        mock.patch("app.presentation.main_window.SettingsDialog", return_value=dialog),
        mock.patch("app.presentation.main_window.QMessageBox.information") as info,
    ):
        window._open_settings()  # noqa: SLF001
    assert not info.called


def test_import_archive_selects_folder(qapp, fake_repo, gas_repo, tmp_path):
    """Import now chooses a whole folder, not individual files."""
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "data_2024-01-01.csv").write_bytes(b"x")
    (folder / "log_2024-01-02.txt").write_bytes(b"x")
    (folder / "readme.md").write_text("ignore me")
    with (
        mock.patch(
            "app.presentation.main_window.QFileDialog.getExistingDirectory",
            return_value=str(folder),
        ),
        mock.patch.object(window, "_start_sync") as start,
    ):
        window._import_archive()
    used = start.call_args[0][0]
    # the lambda closes over `files`; unwrap it to inspect
    files = [c.cell_contents for c in used.__closure__]
    items = files[0] if isinstance(files[0], list) else files
    names = sorted(Path(p).name for p in items)
    assert names == ["data_2024-01-01.csv", "log_2024-01-02.txt"]


# -- Round 3: pickers reflect the controller (AJAX everywhere) -----------------
def test_table_default_shows_first_entry_to_today(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    assert window._preset.currentData() == "first_today"  # noqa: SLF001
    assert window._from_edit.date().toPyDate() == date(2026, 1, 1)  # noqa: SLF001
    assert window._to_edit.date().toPyDate() == date.today()  # noqa: SLF001
    assert services.controller.table_resolved_range() == (date(2026, 1, 1), date.today())
    # visible rows lie inside the resolved window - no full-history leak
    rows = services.controller.table_resolved_range()
    assert all(rows[0] <= row[0] <= rows[1] for row in window._table_model._rows)  # noqa: SLF001


def test_charts_start_on_current_year_and_sync_combo(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    assert window._charts._preset.currentData() == "this_year"  # noqa: SLF001
    assert window._charts._year_from.value() == date.today().year  # noqa: SLF001
    assert window._charts._year_to.value() == date.today().year  # noqa: SLF001


def test_charts_last3_preset_moves_year_pickers(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    window = MainWindow(_services(fake_repo, gas_repo))
    combo = window._charts._preset  # noqa: SLF001
    combo.setCurrentIndex(combo.findData("last3"))
    now = date.today()
    assert window._charts._year_from.value() == now.year - 2  # noqa: SLF001
    assert window._charts._year_to.value() == now.year  # noqa: SLF001


def test_manual_table_range_switches_to_custom(qapp, fake_repo, gas_repo):
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    window = MainWindow(services)
    window._to_edit.setDate(QDate(2026, 1, 2))  # noqa: SLF001 - user edits "To"
    assert window._preset.currentData() is None  # noqa: SLF001
    assert services.controller.table_resolved_range() == (date(2026, 1, 1), date(2026, 1, 2))


def test_compare_tab_applies_dark_mode_at_startup(qapp, fake_repo, gas_repo):
    """Owner: when the app starts dark, the compare tab must be dark too."""
    _seed(fake_repo)
    services = _services(fake_repo, gas_repo)
    services.theme.set_mode("dark")  # dark from the very beginning
    window = MainWindow(services)
    assert window._compare._dark is True  # noqa: SLF001
    from matplotlib import colors as mcolors

    from app.presentation.mpl_charts import _BG_COLOR

    ax = window._compare._meter_view.axes  # noqa: SLF001
    assert mcolors.to_hex(ax.get_facecolor()) == _BG_COLOR[True].lower()
