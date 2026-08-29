"""Manual correction of a single day's reading."""

from __future__ import annotations

from app.application.models import ManualEditRequest
from app.application.use_cases.interpolate import RecomputeInterpolationUseCase
from app.domain.entities import LogCategory, LogLevel
from app.domain.validation import validate_reading_value


class ManualEditUseCase:
    """Set the Modified (adjusted) value; import/interpolated values stay untouched."""

    def __init__(self, repo, logger):
        self._repo = repo
        self._logger = logger

    def run(self, request: ManualEditRequest):
        if not validate_reading_value(request.value):
            raise ValueError(f"Value must be a finite non-negative number, got {request.value}")
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
