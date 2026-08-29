"""CSV parser tests against the real sample logfiles + edge cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.infrastructure.parsing.csv_parser import CsvLogfileParser


def test_csv_sample_2022(samples):
    result = CsvLogfileParser().parse(samples["csv_2022"])
    assert result.value == Decimal("31163.63")
    assert result.day == date(2022, 11, 29)
    assert result.rows_read == 288
    assert result.candidates > 0


def test_csv_sample_2026(samples):
    result = CsvLogfileParser().parse(samples["csv_2026"])
    assert result.value == Decimal("34287.788")
    assert result.day == date(2026, 8, 27)


def test_csv_last_successful_row_wins(tmp_path):
    p = tmp_path / "data_2026-01-01.csv"
    p.write_text(
        "2026-01-01T00:00:00,main,100,100,100,0,0,no error\n"
        "2026-01-01T01:00:00,main,101,101,101,0,0,no error\n"
        "2026-01-01T02:00:00,main,,,101,0,0,Neg. Rate\n",  # error row skipped
        encoding="utf-8",
    )
    result = CsvLogfileParser().parse(p)
    assert result.value == Decimal("101")
    assert result.day == date(2026, 1, 1)


def test_csv_no_usable_reading(tmp_path):
    p = tmp_path / "data_2026-01-01.csv"
    p.write_text(
        "2026-01-01T00:00:00,main,,,101,0,0,Neg. Rate\n"
        "2026-01-01T01:00:00,main,,,101,0,0,Neg. Rate\n",
        encoding="utf-8",
    )
    result = CsvLogfileParser().parse(p)
    assert result.value is None


def test_csv_truncated_graceful(tmp_path):
    p = tmp_path / "data_2026-01-01.csv"
    p.write_bytes(b"2026-01-01T00:00:00,main,100,")  # cut mid-line
    result = CsvLogfileParser().parse(p)
    assert result.value is None


def test_csv_day_fallback_from_timestamp(tmp_path):
    p = tmp_path / "dayfile.csv"  # no date in name
    p.write_text(
        "2026-03-15T00:00:00,main,100,100,100,0,0,no error\n", encoding="utf-8"
    )
    result = CsvLogfileParser().parse(p)
    assert result.day == date(2026, 3, 15)
    assert result.value == Decimal("100")


def test_csv_latin1_fallback(tmp_path):
    p = tmp_path / "data_2026-01-01.csv"
    raw = "2026-01-01T00:00:00,main,100,100,100,0,0,no error\n"
    p.write_bytes(raw.encode("latin-1") + b"\xff\xfe")
    result = CsvLogfileParser().parse(p)
    assert result.value == Decimal("100")
