"""Gas-parameter interval management (calorific value / Z-number per date range).

Adding a new interval automatically closes any predecessor that spans its
``valid_from`` (``valid_to = valid_from - 1 day``) so the transition between
intervals stays seamless and gap-free.
"""

from __future__ import annotations

from datetime import date, timedelta

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
        existing = self._repo.all_intervals()

        # An interval that starts on the same day replaces the existing one
        # (the settings dialog re-emits its rows, incl. the auto-closed
        # predecessor) - otherwise it would be flagged as an overlap.
        replaces = [i for i in existing if i.valid_from == interval.valid_from]
        repairs = self._plan_predecessor_closes(interval, existing)

        # Validate against the post-repair state *before* mutating anything so a
        # rejected upsert never leaves a partially changed state behind.
        touched = {(i.valid_from, i.valid_to) for i in replaces}
        touched |= {(original.valid_from, original.valid_to) for original, _ in repairs}
        simulated = [i for i in existing if (i.valid_from, i.valid_to) not in touched]
        simulated.extend(closed for _, closed in repairs)
        errors = validate_interval(interval, simulated)
        if errors:
            raise ValueError("; ".join(errors))

        for original in replaces:
            self._repo.delete_interval(original.valid_from, original.valid_to)
            self._logger.log(
                LogCategory.GAS_PARAMS,
                LogLevel.INFO,
                f"Replaced interval {original.valid_from} → {original.valid_to or 'open'} "
                f"with {interval.valid_from} → {interval.valid_to or 'open'}",
            )

        for original, closed in repairs:
            self._repo.delete_interval(original.valid_from, original.valid_to)
            self._repo.upsert_interval(closed)
            self._logger.log(
                LogCategory.GAS_PARAMS,
                LogLevel.INFO,
                f"Auto-closed interval {original.valid_from} → {closed.valid_to} "
                f"(new interval starts {interval.valid_from})",
            )
            if interval.valid_to is not None and (
                original.valid_to is None or original.valid_to > interval.valid_to
            ):
                self._logger.log(
                    LogCategory.GAS_PARAMS,
                    LogLevel.WARNING,
                    f"Interval tail after {interval.valid_to} is uncovered — add another "
                    f"interval if it needs parameters",
                )

        self._repo.upsert_interval(interval)
        self._logger.log(
            LogCategory.GAS_PARAMS,
            LogLevel.INFO,
            f"Gas parameter interval {interval.valid_from} → "
            f"{interval.valid_to or 'open'}: cal={interval.calorific_value} "
            f"z={interval.z_value}",
        )

    @staticmethod
    def _plan_predecessor_closes(
        interval: GasParameterInterval,
        existing: list[GasParameterInterval],
    ) -> list[tuple[GasParameterInterval, GasParameterInterval]]:
        """Previous intervals spanning ``interval.valid_from``, closed the day before.

        Intervals that start exactly on ``interval.valid_from`` are not touched
        here - ``upsert`` replaces them wholesale.
        """
        repairs: list[tuple[GasParameterInterval, GasParameterInterval]] = []
        for original in existing:
            if original.valid_from >= interval.valid_from:
                continue
            if original.valid_to is not None and original.valid_to < interval.valid_from:
                continue
            closed = GasParameterInterval(
                valid_from=original.valid_from,
                valid_to=interval.valid_from - timedelta(days=1),
                calorific_value=original.calorific_value,
                z_value=original.z_value,
            )
            repairs.append((original, closed))
        return repairs

    def delete(self, valid_from: date, valid_to: date | None) -> None:
        self._repo.delete_interval(valid_from, valid_to)
        self._logger.log(
            LogCategory.GAS_PARAMS,
            LogLevel.INFO,
            f"Deleted gas parameter interval {valid_from} → {valid_to or 'open'}",
        )
