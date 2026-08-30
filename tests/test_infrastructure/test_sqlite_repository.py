"""SQLite repository tests: round-trip, ON CONFLICT semantics, Decimal fidelity."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import Source
from app.infrastructure.persistence.sqlite_meter_repository import SqliteMeterRepository


def test_round_trip(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_import(date(2026, 1, 1), Decimal("31163.63"))
    reading = repo.get_reading(date(2026, 1, 1))
    assert reading.import_value == Decimal("31163.63")
    assert reading.adjusted_value == Decimal("31163.63")
    assert reading.source == Source.LOGFILE
    assert reading.day == date(2026, 1, 1)
    repo.close()


def test_first_and_latest_reading_day(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    assert repo.first_reading_day() is None
    assert repo.latest_reading_day() is None
    repo.save_import(date(2025, 12, 31), Decimal("100"))
    repo.save_import(date(2026, 1, 3), Decimal("104"))
    repo.save_import(date(2026, 1, 1), Decimal("102"))
    assert repo.first_reading_day() == date(2025, 12, 31)
    assert repo.latest_reading_day() == date(2026, 1, 3)
    repo.close()


def test_save_import_manual_backfill(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_manual(date(2026, 1, 1), Decimal("999"))
    repo.save_import(date(2026, 1, 1), Decimal("31163.63"))
    reading = repo.get_reading(date(2026, 1, 1))
    assert reading.import_value == Decimal("31163.63")
    assert reading.adjusted_value == Decimal("999")
    assert reading.source == Source.MANUAL
    repo.close()


def test_save_interpolated_does_not_override_import(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_import(date(2026, 1, 1), Decimal("100"))
    repo.save_interpolated(date(2026, 1, 1), Decimal("50"))
    reading = repo.get_reading(date(2026, 1, 1))
    assert reading.adjusted_value == Decimal("100")
    assert reading.source == Source.LOGFILE
    repo.close()


def test_save_interpolated_on_free_day(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_interpolated(date(2026, 1, 2), Decimal("110"))
    reading = repo.get_reading(date(2026, 1, 2))
    assert reading.adjusted_value == Decimal("110")
    assert reading.interpolated_value == Decimal("110")
    assert reading.source == Source.INTERPOLATED
    repo.close()


def test_restore_to_original_prefers_import(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_import(date(2026, 1, 1), Decimal("100"))
    repo.save_interpolated(date(2026, 1, 1), Decimal("50"))
    repo.restore_to_original(date(2026, 1, 1))
    reading = repo.get_reading(date(2026, 1, 1))
    assert reading.adjusted_value == Decimal("100")
    repo.close()


def test_all_days_with_import_and_ranges(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_import(date(2026, 1, 1), Decimal("1"))
    repo.save_interpolated(date(2026, 1, 2), Decimal("2"))
    repo.save_import(date(2026, 1, 3), Decimal("3"))
    assert repo.all_days_with_import() == {date(2026, 1, 1), date(2026, 1, 3)}
    assert [r.day for r in repo.get_readings(date(2026, 1, 2), date(2026, 1, 3))] == [
        date(2026, 1, 2), date(2026, 1, 3),
    ]
    assert repo.latest_reading_day() == date(2026, 1, 3)
    repo.close()


def test_reimport_after_manual_backfill_then_restore(sqlite_db):
    repo = SqliteMeterRepository(sqlite_db)
    repo.save_import(date(2026, 1, 1), Decimal("100"))
    repo.save_manual(date(2026, 1, 1), Decimal("105"))
    repo.save_import(date(2026, 1, 1), Decimal("110"))  # backfill again
    reading = repo.get_reading(date(2026, 1, 1))
    assert reading.adjusted_value == Decimal("105")
    repo.restore_to_original(date(2026, 1, 1))
    assert repo.get_reading(date(2026, 1, 1)).adjusted_value == Decimal("110")
    repo.close()


def test_gas_parameter_repository(sqlite_db):
    from decimal import Decimal as D

    from app.domain.entities import GasParameterInterval
    from app.infrastructure.persistence.sqlite_gas_parameter_repository import SqliteGasParameterRepository

    repo = SqliteGasParameterRepository(sqlite_db)
    repo.upsert_interval(
        GasParameterInterval(date(2026, 1, 1), None, D("11.5"), D("0.95"))
    )
    interval = repo.parameter_for(date(2026, 6, 15))
    assert interval is not None
    assert interval.calorific_value == D("11.5")
    assert repo.parameter_for(date(2025, 12, 31)) is None
    repo.close()
