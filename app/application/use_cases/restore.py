"""Restore a day to its original (trusted) value."""

from __future__ import annotations

from datetime import date

from app.application.use_cases.interpolate import RecomputeInterpolationUseCase
from app.domain.entities import LogCategory, LogLevel


class RestoreValueUseCase:
    """Apply the trust hierarchy: modified > imported > interpolated.

    Restoring sets the adjusted value to the logfile import value when present,
    else to the stored/computed interpolated value. If neither exists the day is
    left untouched and a warning is logged.
    """

    def __init__(self, repo, logger):
        self._repo = repo
        self._logger = logger

    def run(self, day: date):
        reading = self._repo.get_reading(day)
        if reading is None:
            self._logger.log(LogCategory.RESTORE, LogLevel.WARNING, f"Restore: no row for {day}")
            return None
        if reading.import_value is not None:
            self._repo.restore_to_original(day)
            self._logger.log(
                LogCategory.RESTORE,
                LogLevel.INFO,
                f"Restored {day} to import value {reading.import_value}",
            )
        elif reading.interpolated_value is not None:
            self._repo.restore_to_original(day)
            self._logger.log(
                LogCategory.RESTORE,
                LogLevel.INFO,
                f"Restored {day} to interpolated value {reading.interpolated_value}",
            )
        else:
            self._logger.log(
                LogCategory.RESTORE,
                LogLevel.WARNING,
                f"Restore {day}: neither import nor interpolated value available; left unchanged",
            )
            return reading
        fills = RecomputeInterpolationUseCase(self._repo, self._logger).run()
        if fills:
            self._logger.log(LogCategory.INTERPOLATE, LogLevel.INFO, f"Re-interpolated {fills} day(s)")
        return self._repo.get_reading(day)
