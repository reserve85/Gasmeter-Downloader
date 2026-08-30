"""Archive import use case tests: any date, move-rule, corrupt stays."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.application.use_cases.sync import ArchiveImportUseCase
from app.domain.entities import Source



def _use_case(fake_repo, parser, archiver, logger):
    return ArchiveImportUseCase(fake_repo, parser, archiver, logger)


def test_import_at_any_date(fake_repo, parser, archiver, logger):
    path = Path("data_2020-05-05.csv")
    parser.add_csv(path, date(2020, 5, 5), Decimal("123.45"))
    result = _use_case(fake_repo, parser, archiver, logger).run([path])

    assert result.imported[0].status == "imported"
    reading = fake_repo.get_reading(date(2020, 5, 5))
    assert reading.import_value == Decimal("123.45")
    assert archiver.is_archived(path)


def test_corrupt_file_stays_in_place(fake_repo, parser, archiver, logger):
    path = Path("data_2020-05-05.csv")
    parser.add_csv(path, date(2020, 5, 5), None)
    result = _use_case(fake_repo, parser, archiver, logger).run([path])

    assert result.imported[0].status == "no-value"
    assert not archiver.is_archived(path)


def test_already_archived_file_not_moved_again(fake_repo, parser, archiver, logger):
    path = Path("data_2020-05-05.csv")
    parser.add_csv(path, date(2020, 5, 5), Decimal("1"))
    archiver._store[path.name] = path  # already archived

    result = _use_case(fake_repo, parser, archiver, logger).run([path])

    assert result.imported[0].status == "imported"
    assert path not in archiver.moved  # no move performed


def test_manual_day_backfill_preserves_override(fake_repo, parser, archiver, logger):
    day = date(2020, 5, 5)
    fake_repo.save_manual(day, Decimal("50"))
    path = Path("data_2020-05-05.csv")
    parser.add_csv(path, day, Decimal("10"))
    _use_case(fake_repo, parser, archiver, logger).run([path])

    reading = fake_repo.get_reading(day)
    assert reading.import_value == Decimal("10")
    assert reading.adjusted_value == Decimal("50")
    assert reading.source == Source.MANUAL
