"""Manual edit use case tests: validation, import untouched, neighbors re-interpolated."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.application.models import ManualEditRequest
from app.application.use_cases.manual_edit import ManualEditUseCase
from app.domain.entities import Source


def test_manual_edit_sets_adjusted_and_source(fake_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    use_case = ManualEditUseCase(fake_repo, logger)

    result = use_case.run(ManualEditRequest(day=date(2026, 1, 1), value=Decimal("105")))

    assert result.adjusted_value == Decimal("105")
    assert result.source == Source.MANUAL
    assert result.import_value == Decimal("100")  # untouched


def test_manual_edit_new_day(fake_repo, logger):
    use_case = ManualEditUseCase(fake_repo, logger)
    result = use_case.run(ManualEditRequest(day=date(2026, 1, 1), value=Decimal("105")))
    assert result.source == Source.MANUAL
    assert result.import_value is None


def test_manual_edit_rejects_negative(fake_repo, logger):
    use_case = ManualEditUseCase(fake_repo, logger)
    with pytest.raises(ValueError):
        use_case.run(ManualEditRequest(day=date(2026, 1, 1), value=Decimal("-1")))


def test_manual_edit_triggers_reinterpolation(fake_repo, logger):
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 1, 4), Decimal("130"))
    # pre-fill the gap so the dataset is complete
    from app.application.use_cases.interpolate import RecomputeInterpolationUseCase

    RecomputeInterpolationUseCase(fake_repo, logger).run()
    use_case = ManualEditUseCase(fake_repo, logger)
    # move boundary: day 1 becomes 110 -> interior days recompute to 116.667/123.333
    use_case.run(ManualEditRequest(day=date(2026, 1, 1), value=Decimal("110")))

    assert fake_repo.get_reading(date(2026, 1, 2)).adjusted_value == Decimal("116.667")
    assert fake_repo.get_reading(date(2026, 1, 3)).adjusted_value == Decimal("123.333")
