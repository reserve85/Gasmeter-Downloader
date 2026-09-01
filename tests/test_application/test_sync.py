"""Sync use case tests: window, 404, interpolation chaining, manual-day backfill."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path


from app.application.use_cases.sync import SyncMissingLogfilesUseCase
from app.domain.entities import LogCategory, Source

from tests.conftest import FakeSettings


def _use_case(fake_repo, source, parser, archiver, logger, clock, settings=None):
    if settings is None:
        settings = FakeSettings({"device.max_download_days": 30, "paths.download": "downloads"})
    return SyncMissingLogfilesUseCase(
        fake_repo, source, parser, archiver, settings, logger, clock
    )


def test_yesterday_missing_downloaded_imported_archived(
    fake_repo, source, parser, archiver, logger, clock, tmp_path
):
    settings = {"device.max_download_days": 30, "paths.download": str(tmp_path / "downloads")}
    day = date(2026, 8, 28)
    source.available.add(day)
    source.payloads[day] = b"data"
    parser.add_csv(Path("data_2026-08-28.csv"), day, Decimal("31163.63"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock, settings).run()

    assert result.downloaded == [day]
    assert result.imported[0].status == "imported"
    assert day not in result.missing_on_device  # other window days are absent on device
    assert result.failed == []
    assert archiver.is_archived(Path(f"data_{day.isoformat()}.csv"))
    reading = fake_repo.get_reading(day)
    assert reading is not None
    assert reading.import_value == Decimal("31163.63")
    assert reading.source == Source.LOGFILE


def test_today_never_downloaded(fake_repo, source, parser, archiver, logger, clock):
    day = date(2026, 8, 29)  # == clock.today()
    source.available.add(day)
    source.payloads[day] = b"data"
    parser.add_csv(Path("data_2026-08-29.csv"), day, Decimal("10"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()

    assert day not in result.downloaded
    assert fake_repo.get_reading(day) is None
    assert logger.messages_of(LogCategory.IGNORE)


def test_already_present_day_skipped(fake_repo, source, parser, archiver, logger, clock):
    day = date(2026, 8, 28)
    fake_repo.save_import(day, Decimal("100"))
    source.payloads[day] = b"data"
    parser.add_csv(Path("data_2026-08-28.csv"), day, Decimal("100"))
    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()

    assert result.downloaded == []
    assert result.imported == []
    reading = fake_repo.get_reading(day)
    assert reading.import_value == Decimal("100")


def test_404_becomes_missing_on_device(fake_repo, source, parser, archiver, logger, clock):
    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()
    assert date(2026, 8, 28) in result.missing_on_device
    assert logger.messages_of(LogCategory.IGNORE)


def test_configurable_window(fake_repo, source, parser, archiver, logger, clock):
    day = date(2026, 8, 27)
    source.payloads[day] = b"data"
    parser.add_csv(Path("data_2026-08-27.csv"), day, Decimal("1"))
    settings = {"device.max_download_days": 2, "paths.download": "downloads"}
    result = _use_case(fake_repo, source, parser, archiver, logger, clock, settings).run()

    assert result.downloaded == [day]
    assert date(2026, 8, 28) in result.missing_on_device
    assert fake_repo.get_reading(date(2026, 8, 26)) is None


def test_unparsable_file_failed_not_archived(fake_repo, source, parser, archiver, logger, clock, tmp_path):
    day = date(2026, 8, 28)
    settings = {"device.max_download_days": 30, "paths.download": str(tmp_path / "downloads")}
    source.payloads[day] = b"corrupt"
    parser.add_csv(Path("data_2026-08-28.csv"), day, None)

    result = _use_case(fake_repo, source, parser, archiver, logger, clock, settings).run()

    assert day in result.downloaded
    assert result.imported[0].status == "no-value"
    assert not archiver.is_archived(Path("data_2026-08-28.csv"))
    assert fake_repo.get_reading(day) is None


def test_import_into_manual_day_backfills_import_only(
    fake_repo, source, parser, archiver, logger, clock
):
    day = date(2026, 8, 28)
    fake_repo.save_manual(day, Decimal("99.5"))
    source.payloads[day] = b"data"
    parser.add_csv(Path("data_2026-08-28.csv"), day, Decimal("77.0"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()

    assert result.imported[0].status == "imported"
    reading = fake_repo.get_reading(day)
    assert reading.import_value == Decimal("77.0")
    assert reading.adjusted_value == Decimal("99.5")  # modified > imported
    assert reading.source == Source.MANUAL


def test_device_listing_prefilters(fake_repo, source, parser, archiver, logger, clock):
    listed = date(2026, 8, 28)
    not_listed = date(2026, 8, 27)
    source.available = {listed}
    source.payloads[listed] = b"data"
    source.payloads[not_listed] = b"data"  # present but NOT listed
    parser.add_csv(Path("data_2026-08-27.csv"), not_listed, Decimal("1"))
    parser.add_csv(Path("data_2026-08-28.csv"), listed, Decimal("2"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()

    assert not_listed in result.missing_on_device
    assert listed in result.downloaded
    assert not_listed not in result.downloaded


def test_interpolation_runs_after_import(fake_repo, source, parser, archiver, logger, clock):
    day1 = date(2026, 8, 25)
    day2 = date(2026, 8, 28)
    source.payloads[day1] = b"data"
    source.payloads[day2] = b"data"
    parser.add_csv(Path("data_2026-08-25.csv"), day1, Decimal("100"))
    parser.add_csv(Path("data_2026-08-28.csv"), day2, Decimal("130"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock).run()

    assert len(result.downloaded) == 2
    middle = fake_repo.get_reading(date(2026, 8, 27))
    assert middle is not None
    assert middle.source == Source.INTERPOLATED
    assert middle.adjusted_value == Decimal("120")


def test_sync_imports_from_archive_instead_of_downloading(
    fake_repo, source, parser, archiver, logger, clock, tmp_path
):
    """When the archive already has a file for a missing day, the sync imports
    from the archive instead of downloading from the device — no duplicates."""
    settings = {"device.max_download_days": 30, "paths.download": str(tmp_path / "downloads")}
    day = date(2026, 8, 28)

    # Simulate: archive already has the file (e.g. from a previous run).
    archive_file = tmp_path / "archive" / f"data_{day.isoformat()}.csv"
    archive_file.parent.mkdir()
    archive_file.write_text("archived content")
    archiver._store[archive_file.name] = archive_file

    # Device also has it — but it should NOT be downloaded.
    source.available.add(day)
    source.payloads[day] = b"device content"
    parser.add_csv(archive_file, day, Decimal("31163.63"))

    result = _use_case(fake_repo, source, parser, archiver, logger, clock, settings).run()

    # Imported from archive, not downloaded.
    assert result.downloaded == []
    assert result.imported[0].status == "imported"
    assert day not in result.missing_on_device
    assert fake_repo.get_reading(day) is not None
    assert fake_repo.get_reading(day).import_value == Decimal("31163.63")
    # The device was never contacted for this day.
    assert day not in source.download_calls
