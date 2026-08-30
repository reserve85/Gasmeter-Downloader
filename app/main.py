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
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

#: Short delay before the startup update check so the window is fully drawn
#: and the status bar shows "Ready" first (mirrors MusicSceneReleaser).
_UPDATE_CHECK_DELAY_MS = 2000

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PyQt6.QtCore import QLockFile, QTimer  # noqa: E402
from PyQt6.QtGui import QIcon  # noqa: E402
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
from app.infrastructure.filesystem.paths import base_dir, default_dirs, ensure_dirs, icon_path
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


def open_database(db_path):
    """Open SQLite repositories."""
    return SqliteMeterRepository(db_path), SqliteGasParameterRepository(db_path)


def _migrate_legacy_token(settings, crypto, logger) -> None:
    """Guarantee ``update.token`` is never stored in clear text.

    Older builds could leave a plain-text token or the obsolete
    ``.gasmeter_token_key`` ciphertext in the config. Both are migrated to the
    current machine-derived encryption and the key file is removed.
    """
    raw = settings.get("update.token")
    if not raw:
        crypto.remove_legacy_key_file()
        return
    if not TokenCrypto.is_encrypted(str(raw)):
        settings.set("update.token", crypto.encrypt(str(raw)))
        logger.log(
            LogCategory.SETTINGS,
            LogLevel.WARNING,
            "Migrated GitHub token to encrypted storage (was stored in clear text)",
        )
    else:
        rekeyed = crypto.reencrypt_if_legacy(str(raw))
        if rekeyed is not None:
            settings.set("update.token", rekeyed)
            logger.log(
                LogCategory.SETTINGS,
                LogLevel.INFO,
                "Re-encrypted GitHub token with current machine key",
            )
    crypto.remove_legacy_key_file()


def seed_gas_parameters(params_repo, settings, meter_repo) -> None:
    """Guarantee gas-parameter coverage from the first stored logfile on.

    Runs at startup and repairs the existing state:
    - no interval at all      -> create ``(first_reading_day, open)``;
    - earliest interval starts AFTER the first logfile -> prepend a leading
      interval so coverage reaches back to the very first day;
    - the last interval is bounded but readings exist after its end -> reopen
      it so ``bis heute`` stays covered.
    """
    intervals = params_repo.all_intervals()
    first_day = meter_repo.first_reading_day() or meter_repo.latest_reading_day()
    if first_day is None:
        return
    default_cal = Decimal(str(settings.get("gas.default_calorific", 11.342)))
    default_z = Decimal(str(settings.get("gas.default_z_value", 0.9589)))

    if not intervals:
        params_repo.upsert_interval(
            GasParameterInterval(first_day, None, default_cal, default_z)
        )
        return

    earliest = intervals[0]
    if earliest.valid_from > first_day:
        params_repo.upsert_interval(
            GasParameterInterval(
                valid_from=first_day,
                valid_to=earliest.valid_from - timedelta(days=1),
                calorific_value=default_cal,
                z_value=default_z,
            )
        )
    latest = meter_repo.latest_reading_day()
    last = intervals[-1]
    if latest is not None and last.valid_to is not None and last.valid_to < latest:
        # the PK is (valid_from, valid_to): an open-ended row is a DIFFERENT
        # key than the bounded one, so delete first, then insert the open row.
        params_repo.delete_interval(last.valid_from, last.valid_to)
        params_repo.upsert_interval(
            GasParameterInterval(
                valid_from=last.valid_from,
                valid_to=None,
                calorific_value=last.calorific_value,
                z_value=last.z_value,
            )
        )


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
    theme.set_mode(str(settings.get("theme.mode", "auto")))

    # application icon (title bar, taskbar, dialogs)
    icon = QIcon(str(icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)

    db_path = settings.get("paths.database")
    meter_repo, params_repo = open_database(db_path)
    seed_gas_parameters(params_repo, settings, meter_repo)

    parser = LogfileParser()
    archiver = FileArchiver(Path(settings.get("paths.archive")))
    client = HttpLogfileClient(str(settings.get("device.ip", "192.168.10.65")))
    clock = SystemClock()
    update_adapter = build_update_service()
    update_adapter.clean_old_files()
    token_crypto = TokenCrypto(dirs["config"] / ".gasmeter_token_key")
    _migrate_legacy_token(settings, token_crypto, logger)

    sync_use_case = SyncMissingLogfilesUseCase(
        meter_repo, client, parser, archiver, settings, logger, clock
    )
    archive_use_case = ArchiveImportUseCase(meter_repo, parser, archiver, logger)
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
        archiver=archiver,
        version=__version__,
        controller=controller,
        query_use_case=query_use_case,
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

    if settings.get("device.auto_fetch_on_startup", False):
        QTimer.singleShot(0, window.trigger_startup_sync)
    # update check shortly after the window is shown (MusicSceneReleaser pattern);
    # works without a token because the repo is public.
    QTimer.singleShot(_UPDATE_CHECK_DELAY_MS, window.trigger_startup_update_check)

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
