"""Gas-parameter interval management (calorific value / Z-number per date range)."""

from __future__ import annotations

from datetime import date

from app.application.models import ParamsIntervalRequest
from app.domain.entities import GasParameterInterval, LogCategory, LogLevel
from app.domain.validation import validate_interval


class GasParametersUseCase:
    def __init__(self, repo, logger):
        self._repo = repo
        self._logger = logger

    def list(self) -> list[GasParameterInterval]:
        return self._repo.all_intervals()

    def upsert(self, request: ParamsIntervalRequest) -> None:
        interval = GasParameterInterval(
            valid_from=request.valid_from,
            valid_to=request.valid_to,
            calorific_value=request.calorific_value,
            z_value=request.z_value,
        )
        errors = validate_interval(interval, self._repo.all_intervals())
        if errors:
            raise ValueError("; ".join(errors))
        self._repo.upsert_interval(interval)
        self._logger.log(
            LogCategory.GAS_PARAMS,
            LogLevel.INFO,
            f"Gas parameter interval {interval.valid_from} → "
            f"{interval.valid_to or 'open'}: cal={interval.calorific_value} "
            f"z={interval.z_value}",
        )

    def delete(self, valid_from: date, valid_to: date | None) -> None:
        self._repo.delete_interval(valid_from, valid_to)
        self._logger.log(
            LogCategory.GAS_PARAMS,
            LogLevel.INFO,
            f"Deleted gas parameter interval {valid_from} → {valid_to or 'open'}",
        )
