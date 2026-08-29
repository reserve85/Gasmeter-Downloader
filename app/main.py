#!/usr/bin/env python3
# ruff: noqa: E402  - imports below must follow the sys.path bootstrap
"""Composition root - builds and wires the whole application.

Order: single-instance guard -> directories -> settings -> logger ->
theme -> database + repositories -> parsers/client/archiver -> use cases ->
translator/controller -> main window. ``main()`` is the PyInstaller entry point.

The module is importable both as ``python -m app.main`` and as
``python app/main.py`` (the script form inserts the project root on sys.path).
"""

from __future__ import annotations

import sys
import traceback
from decimal import Decimal
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PyQt6.QtCore import QLockFile  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import __version__
from app.application.use_cases.gas_parameters import GasParametersUseCase
from app.application.use_cases.manual_edit import ManualEditUseCase
from app.application.use_cases.query import GetDashboardUseCase
from app.application.use_cases.restore import RestoreValueUseCase
from app.application.use_cases.settings import SettingsUseCase
from app.application.use_cases.sync import ArchiveImportUseCase, SyncMissingLogfilesUseCase
from app.application.use_cases.updates import ApplyUpdateUseCase, CheckForUpdatesUseCase
from app.domain.entities import GasParameterInterval, LogCategory, LogLevel
from app.infrastructure.clock import SystemClock
from app.infrastructure.config.config_repository import YamlAppSettings
from app.infrastructure.config.security import TokenCrypto
from app.infrastructure.filesystem.file_archiver import FileArchiver
from app.infrastructure.filesystem.paths import base_dir, default_dirs, ensure_dirs
from app.infrastructure.logging.app_logger import AppLogger
from app.infrastructure.parsing.logfile_parser import LogfileParser
from app.infrastructure.persistence.sqlite_gas_parameter_repository import SqliteGasParameterRepository
from app.infrastructure.persistence.sqlite_meter_repository import SqliteMeterRepository
from app.infrastructure.sources.http_logfile_client import HttpLogfileClient
from app.infrastructure.theme.windows_theme import WindowsTheme
from app.infrastructure.updating.update_adapter import GithubUpdateAdapter
from app.presentation.dashboard_controller import DashboardController
from app.presentation.i18n import Translator
from app.presentation.main_window import MainWindow


class AppServices:
    """Bundle of every service/use case the UI needs."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _resolve_language(lang: str) -> str:
    if lang != "auto":
        return lang if lang in ("en", "de") else "en"
    primary = _windows_primary_language()
    if primary == 7:  # LANG_GERMAN
        return "de"
    return "en"


def _windows_primary_language() -> int | None:
    """Best-effort primary Windows UI language id (0x07 = German)."""
    try:
        import ctypes

        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return int(lang_id) & 0x3FF
    except Exception:  # noqa: BLE001
        return None


def open_database(settings, db_path):
    """Open SQLite repositories (settings unused; kept for interface clarity)."""
    return SqliteMeterRepository(db_path), SqliteGasParameterRepository(db_path)


def seed_gas_parameters(params_repo, settings, meter_repo) -> None:
    if params_repo.all_intervals():
        return
    earliest = meter_repo.latest_reading_day()
    if earliest is None:
        return
    interval = GasParameterInterval(
        valid_from=earliest,
        valid_to=None,
        calorific_value=Decimal(str(settings.get("gas.default_calorific", 11.342))),
        z_value=Decimal(str(settings.get("gas.default_z_value", 0.9589))),
    )
    params_repo.upsert_interval(interval)


def build_update_service() -> GithubUpdateAdapter:
    return GithubUpdateAdapter()
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GasmeterDownloader")

    lock_file = QLockFile(str(base_dir() / "gasmeter.lock"))
    if not lock_file.tryLock(100):
        sys.exit(0)  # another instance is running

    dirs = default_dirs()
    ensure_dirs(dirs)
    config_path = dirs["config"] / "app_config.yaml"
    settings = YamlAppSettings(config_path, base=base_dir())

    logger = AppLogger()
    logger.log(LogCategory.STARTUP, LogLevel.INFO, f"Gasmeter Downloader {__version__} starting")
    logger.log(LogCategory.STARTUP, LogLevel.DEBUG, f"Base dir: {base_dir()}")

    theme = WindowsTheme(app)

    db_path = settings.get("paths.database")
    meter_repo, params_repo = open_database(settings, db_path)
    seed_gas_parameters(params_repo, settings, meter_repo)

    parser = LogfileParser()
    archiver = FileArchiver(Path(settings.get("paths.archive")))
    client = HttpLogfileClient(str(settings.get("device.ip", "192.168.10.65")))
    clock = SystemClock()
    update_adapter = build_update_service()
    update_adapter.clean_old_files()
    token_crypto = TokenCrypto(dirs["config"] / ".gasmeter_token_key")

    sync_use_case = SyncMissingLogfilesUseCase(
        meter_repo, params_repo, client, parser, archiver, settings, logger, clock
    )
    archive_use_case = ArchiveImportUseCase(meter_repo, params_repo, parser, archiver, logger, clock)
    manual_use_case = ManualEditUseCase(meter_repo, logger)
    restore_use_case = RestoreValueUseCase(meter_repo, logger)
    settings_use_case = SettingsUseCase(settings, logger, token_crypto)
    gas_params_use_case = GasParametersUseCase(params_repo, logger)
    check_updates_use_case = CheckForUpdatesUseCase(update_adapter, settings, logger, token_crypto)
    apply_update_use_case = ApplyUpdateUseCase(update_adapter, logger)
    query_use_case = GetDashboardUseCase(meter_repo, params_repo, settings, logger)

    tr = Translator(_resolve_language(str(settings.get("app.language", "auto"))))
    controller = DashboardController(query_use_case, settings, logger, tr)

    dark = theme.current_is_dark()
    theme.apply(app, dark)
    theme.log_theme(logger, dark)

    services = AppServices(
        tr=tr,
        settings=settings,
        logger=logger,
        theme=theme,
        app=app,
        repo=meter_repo,
        version=__version__,
        controller=controller,
        sync_use_case=sync_use_case,
        archive_import_use_case=archive_use_case,
        manual_edit_use_case=manual_use_case,
        restore_use_case=restore_use_case,
        settings_use_case=settings_use_case,
        gas_parameters_use_case=gas_params_use_case,
        check_updates_use_case=check_updates_use_case,
        apply_update_use_case=apply_update_use_case,
    )

    window = MainWindow(services)
    window.show()

    def _excepthook(exc_type, exc_value, exc_tb):
        logger.log(
            LogCategory.ERROR,
            LogLevel.CRITICAL,
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = _excepthook

    exit_code = app.exec()
    logger.log(LogCategory.SHUTDOWN, LogLevel.INFO, "Shutting down")
    try:
        theme._timer.stop()  # noqa: SLF001 - clean Qt shutdown
    except Exception:  # noqa: BLE001
        pass
    window.deleteLater()
    meter_repo.close()
    params_repo.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
