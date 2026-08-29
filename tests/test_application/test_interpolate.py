"""Interpolation use case tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.application.use_cases.interpolate import RecomputeInterpolationUseCase



def test_fills_boundary_bounded_gap(fake_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 4), Decimal("130"))
    use_case = RecomputeInterpolationUseCase(fake_repo, logger)

    count = use_case.run()

    assert count == 2
    assert fake_repo.get_reading(date(2026, 1, 2)).adjusted_value == Decimal("110")
    assert fake_repo.get_reading(date(2026, 1, 3)).adjusted_value == Decimal("120")


def test_idempotent(fake_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 4), Decimal("130"))
    use_case = RecomputeInterpolationUseCase(fake_repo, logger)
    assert use_case.run() == 2
    assert use_case.run() == 0  # nothing new to do
    assert fake_repo.get_reading(date(2026, 1, 2)).adjusted_value == Decimal("110")


def test_never_touches_manual_or_logfile(fake_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_manual(date(2026, 1, 2), Decimal("999"))
    fake_repo.save_import(date(2026, 1, 3), Decimal("130"))
    use_case = RecomputeInterpolationUseCase(fake_repo, logger)

    assert use_case.run() == 0
    assert fake_repo.get_reading(date(2026, 1, 2)).adjusted_value == Decimal("999")
