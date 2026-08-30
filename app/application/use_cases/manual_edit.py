"""Manual correction of a single day's reading."""

from __future__ import annotations

from datetime import timedelta

from app.application.models import ManualEditRequest
from app.application.use_cases.interpolate import RecomputeInterpolationUseCase
from app.domain.entities import LogCategory, LogLevel
from app.domain.validation import validate_ascending_order


class ManualEditUseCase:
    """Set the Modified (adjusted) value; import/interpolated values stay untouched.

    The meter reading is a strictly non-decreasing series: a corrected value must
    fit between its neighbours (inclusive). Violations are rejected before any write.
    """

    def __init__(self, repo, logger):
        self._repo = repo
        self._logger = logger

    def run(self, request: ManualEditRequest):
        prev_reading = self._repo.get_reading(request.day - timedelta(days=1))
        next_reading = self._repo.get_reading(request.day + timedelta(days=1))
        errors = validate_ascending_order(
            prev_reading.adjusted_value if prev_reading else None,
            request.value,
            next_reading.adjusted_value if next_reading else None,
        )
        if errors:
            self._logger.log(
                LogCategory.EDIT,
                LogLevel.WARNING,
                f"Manual edit rejected for {request.day}: {'; '.join(errors)}",
            )
            raise ValueError("; ".join(errors))
        self._repo.save_manual(request.day, request.value)
        self._logger.log(
            LogCategory.EDIT,
            LogLevel.INFO,
            f"Manual edit: {request.day} modified value -> {request.value}",
        )
        fills = RecomputeInterpolationUseCase(self._repo, self._logger).run()
        if fills:
            self._logger.log(LogCategory.INTERPOLATE, LogLevel.INFO, f"Re-interpolated {fills} day(s)")
        return self._repo.get_reading(request.day)
