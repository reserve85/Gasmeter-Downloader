"""Sync & archive-import orchestration.

Core flow for device sync: detect missing days within the configured window,
download each from the device, parse, import into SQLite, archive the file,
then re-run interpolation. Every step is logged through the EventLogger.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.application.use_cases.interpolate import RecomputeInterpolationUseCase
from app.domain.entities import (
    DayReading,
    ImportOutcome,
    LogCategory,
    LogLevel,
    Source,
    SyncResult,
)
from app.domain.validation import validate_reading_value


def import_logfile(repo, parser, logger, path: Path) -> ImportOutcome:
    """Parse ``path`` and store the reading. Shared by device sync + archive import.

    Rules:
    - a manual day only gets its ``import_value`` backfilled (modified > imported);
    - a day that already has an import value is reported as ``already-present``;
    - a file with no usable value is reported as ``no-value`` and not archived.
    """
    result = parser.parse(path)
    logger.log(
        LogCategory.PARSE,
        LogLevel.INFO,
        f"Parsed {path.name}: day={result.day}, rows={result.rows_read}, "
        f"candidates={result.candidates} ({result.note})",
    )
    if result.value is None:
        return ImportOutcome(
            day=result.day,
            status="no-value",
            value=None,
            note=f"no usable reading in {path.name}",
        )
    if not validate_reading_value(result.value):
        return ImportOutcome(
            day=result.day,
            status="no-value",
            value=result.value,
            note="parsed value failed plausibility check",
        )
    existing: DayReading | None = repo.get_reading(result.day)
    if existing is not None and existing.source == Source.MANUAL:
        repo.save_import(result.day, result.value)
        outcome = ImportOutcome(
            day=result.day,
            status="imported",
            value=result.value,
            note="backfilled import value; manual modification kept",
        )
    elif existing is not None and existing.import_value is not None:
        outcome = ImportOutcome(
            day=result.day,
            status="already-present",
            value=result.value,
            note="import value already present",
        )
    else:
        repo.save_import(result.day, result.value)
        outcome = ImportOutcome(
            day=result.day,
            status="imported",
            value=result.value,
            note=f"imported value {result.value}",
        )
    logger.log(
        LogCategory.IMPORT,
        LogLevel.INFO,
        f"{outcome.status}: {result.day} = {outcome.value} ({outcome.note})",
    )
    return outcome


class SyncMissingLogfilesUseCase:
    """Download missing daily logfiles from the device within a configurable window."""

    def __init__(
        self,
        repo,
        params_repo,
        source,
        parser,
        archiver,
        settings,
        logger,
        clock,
    ):
        self._repo = repo
        self._params_repo = params_repo
        self._source = source
        self._parser = parser
        self._archiver = archiver
        self._settings = settings
        self._logger = logger
        self._clock = clock

    def run(self) -> SyncResult:
        today = self._clock.today()
        window = int(self._settings.get("device.max_download_days", 30))
        missing = self._missing_days(today, window)
        if not missing:
            self._logger.log(LogCategory.IGNORE, LogLevel.INFO, "No missing logfiles in window")
            return SyncResult([], [], [], [], [])

        self._logger.log(
            LogCategory.DOWNLOAD,
            LogLevel.INFO,
            f"Missing {len(missing)} day(s) in the last {window} days",
        )

        downloaded: list[date] = []
        imported: list[ImportOutcome] = []
        missing_on_device: list[date] = []
        failed: list[tuple[date, str]] = []
        archived: list[Path] = []

        candidates = self._filter_by_device_listing(missing, missing_on_device)
        for day in sorted(candidates):
            try:
                path = self._download_one(day)
            except Exception as exc:  # noqa: BLE001 - any transport failure must be surfaced
                failed.append((day, str(exc)))
                continue
            if path is None:
                missing_on_device.append(day)
                continue
            downloaded.append(day)
            outcome = import_logfile(self._repo, self._parser, self._logger, path)
            imported.append(outcome)
            if outcome.status in ("imported", "already-present") and outcome.value is not None:
                moved = self._archive(path)
                if moved is not None:
                    archived.append(moved)

        fills = RecomputeInterpolationUseCase(self._repo, self._logger).run()
        self._logger.log(
            LogCategory.INTERPOLATE,
            LogLevel.INFO,
            f"Interpolation recomputed: {fills} day(s) filled",
        )
        return SyncResult(downloaded, imported, missing_on_device, failed, archived)

    def _filter_by_device_listing(self, missing: list[date], missing_on_device: list[date]) -> list[date]:
        try:
            device_days = set(self._source.available_days())
        except Exception as exc:  # noqa: BLE001
            self._logger.log(
                LogCategory.DOWNLOAD,
                LogLevel.WARNING,
                f"Device listing unavailable ({exc}); attempting downloads anyway",
            )
            return missing
        if not device_days:
            return missing
        candidates: list[date] = []
        for day in missing:
            if day in device_days:
                candidates.append(day)
            else:
                missing_on_device.append(day)
                self._logger.log(
                    LogCategory.IGNORE,
                    LogLevel.WARNING,
                    f"{day} not present on device",
                )
        return candidates

    def _missing_days(self, today: date, window: int) -> list[date]:
        """Window = ``max_download_days`` up to yesterday; today is always skipped."""
        end = today - timedelta(days=1)
        start = end - timedelta(days=window - 1)
        known = self._repo.all_days_with_import()
        self._logger.log(LogCategory.IGNORE, LogLevel.INFO, "Skipping today (not yet complete)")
        missing: list[date] = []
        day = start
        while day <= end:
            if day not in known:
                missing.append(day)
            day += timedelta(days=1)
        return missing

    def _download_one(self, day: date) -> Path | None:
        """HTTP GET for the day; None on 404/not listed. Raises on transport errors."""
        target = Path(self._settings.get("paths.download"))
        path = self._source.download(day, target)
        if path is not None:
            self._logger.log(LogCategory.DOWNLOAD, LogLevel.INFO, f"Downloaded {day}: {path.name}")
        return path

    def _archive(self, path: Path) -> Path | None:
        try:
            moved = self._archiver.archive(path)
        except OSError as exc:
            self._logger.log(LogCategory.ARCHIVE, LogLevel.ERROR, f"Archive failed for {path.name}: {exc}")
            return None
        if moved is not None:
            self._logger.log(LogCategory.ARCHIVE, LogLevel.INFO, f"Archived {moved}")
        return moved


class ArchiveImportUseCase:
    """Import user-selected logfiles (archive, downloads/, USB, …) at any date."""

    def __init__(self, repo, params_repo, parser, archiver, logger, clock):
        self._repo = repo
        self._params_repo = params_repo
        self._parser = parser
        self._archiver = archiver
        self._logger = logger
        self._clock = clock

    def run(self, files: list[Path]) -> SyncResult:
        imported: list[ImportOutcome] = []
        missing_on_device: list[date] = []
        failed: list[tuple[date, str]] = []
        archived: list[Path] = []

        for path in sorted(files):
            try:
                outcome = import_logfile(self._repo, self._parser, self._logger, path)
            except Exception as exc:  # noqa: BLE001
                failed.append((path.name, str(exc)))
                continue
            imported.append(outcome)
            if outcome.status in ("imported", "already-present") and outcome.value is not None:
                # Files already inside the archive folder are never moved again;
                # everything else is moved after a successful import.
                if not self._archiver.is_archived(path):
                    moved = self._archiver.archive(path)
                    if moved is not None:
                        archived.append(moved)

        fills = RecomputeInterpolationUseCase(self._repo, self._logger).run()
        self._logger.log(
            LogCategory.INTERPOLATE,
            LogLevel.INFO,
            f"Interpolation recomputed: {fills} day(s) filled",
        )
        return SyncResult([], imported, missing_on_device, failed, archived)
