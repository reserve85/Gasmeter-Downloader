"""TXT parser tests against the real legacy sample + edge cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.infrastructure.parsing.text_parser import TextLogfileParser


def test_txt_sample(samples):
    result = TextLogfileParser().parse(samples["txt_2022"])
    assert result.value == Decimal("31136.93")
    assert result.day == date(2022, 11, 20)
    assert result.rows_read > 280


def test_txt_last_match_wins(tmp_path):
    p = tmp_path / "log_2022-11-20.txt"
    p.write_text(
        "2022-11-20T00:00:00: PostProcessing - Raw: 1.0 Value: 1.0 Error: no error\n"
        "2022-11-20T00:05:00: PostProcessing - Raw: 2.0 Value: 2.0 Error: no error\n"
        "2022-11-20T00:06:00: PostProcessing - Raw: 3.0 Value: 3.0 Error: something\n",
        encoding="utf-8",
    )
    result = TextLogfileParser().parse(p)
    assert result.value == Decimal("2.0")
    assert result.day == date(2022, 11, 20)


def test_txt_no_match_graceful(tmp_path):
    p = tmp_path / "log_2022-11-20.txt"
    p.write_text("nothing useful here\n", encoding="utf-8")
    result = TextLogfileParser().parse(p)
    assert result.value is None
    assert result.day is not None  # fallback day from filename


def test_txt_day_fallback_from_timestamp_line(tmp_path):
    p = tmp_path / "legacy.txt"
    p.write_text(
        "2022-11-20T00:00:00: some line\n"
        "2022-11-20T00:05:00: PostProcessing - Raw: 5.0 Value: 5.0 Error: no error\n",
        encoding="utf-8",
    )
    result = TextLogfileParser().parse(p)
    assert result.day == date(2022, 11, 20)
    assert result.value == Decimal("5.0")
