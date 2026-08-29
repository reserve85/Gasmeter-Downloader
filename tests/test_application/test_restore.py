"""Restore use case tests: import wins, interpolated fallback, warning path."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import LogCategory, Source


def test_restore_to_import_value(fake_repo, logger):
    from app.application.use_cases.restore import RestoreValueUseCase

    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_manual(date(2026, 1, 1), Decimal("999"))

    result = RestoreValueUseCase(fake_repo, logger).run(date(2026, 1, 1))

    assert result.adjusted_value == Decimal("100")
    assert result.source == Source.LOGFILE


def test_restore_without_import_uses_interpolated(fake_repo, logger):
    from app.application.use_cases.restore import RestoreValueUseCase

    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("130"))
    from app.application.use_cases.interpolate import RecomputeInterpolationUseCase

    RecomputeInterpolationUseCase(fake_repo, logger).run()  # 2026-01-02 interpolated
    fake_repo.save_manual(date(2026, 1, 2), Decimal("0"))  # user override

    result = RestoreValueUseCase(fake_repo, logger).run(date(2026, 1, 2))

    assert result.adjusted_value == Decimal("115")
    assert result.source == Source.INTERPOLATED


def test_restore_with_no_reference_logs_warning(fake_repo, logger):
    from app.application.use_cases.restore import RestoreValueUseCase

    fake_repo.save_manual(date(2026, 1, 2), Decimal("50"))
    result = RestoreValueUseCase(fake_repo, logger).run(date(2026, 1, 2))
    assert result.adjusted_value == Decimal("50")
    assert logger.messages_of(LogCategory.RESTORE)


def test_restore_missing_day_returns_none(fake_repo, logger):
    from app.application.use_cases.restore import RestoreValueUseCase

    assert RestoreValueUseCase(fake_repo, logger).run(date(2026, 1, 2)) is None
