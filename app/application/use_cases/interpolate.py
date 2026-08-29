"""Recompute interpolation after every data mutation (idempotent)."""

from __future__ import annotations

from app.domain.entities import LogCategory, LogLevel
from app.domain.interpolation import recompute_gaps


class RecomputeInterpolationUseCase:
    """Fill any boundary-bounded gap; only touches days with no row or source=INTERPOLATED."""

    def __init__(self, repo, logger):
        self._repo = repo
        self._logger = logger

    def run(self) -> int:
        readings = self._repo.get_readings(None, None)
        fills = recompute_gaps(readings)
        applied = 0
        for fill in fills:
            self._repo.save_interpolated(fill.day, fill.value)
            applied += 1
        if applied:
            self._logger.log(
                LogCategory.INTERPOLATE,
                LogLevel.INFO,
                f"Interpolated {applied} day(s): "
                + ", ".join(f"{f.day}={f.value}" for f in fills[:5])
                + ("…" if applied > 5 else ""),
            )
        return applied
