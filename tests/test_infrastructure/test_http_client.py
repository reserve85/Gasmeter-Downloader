"""Device listing parser tests + HTTP client tests (mocked urlopen)."""

from __future__ import annotations

from datetime import date
from unittest import mock

from app.infrastructure.sources.device_listing_parser import day_from_filename, parse_listing
from app.infrastructure.sources.http_logfile_client import HttpLogfileClient

LISTING_HTML = """
<html><body>
<a href="data_2026-08-25.csv">data_2026-08-25.csv</a>
<a href="data_2026-08-26.csv">data_2026-08-26.csv</a>
<a href="data_2026-08-27.csv">data_2026-08-27.csv</a>
<a href="readme.txt">readme.txt</a>
</body></html>
"""


def test_parse_listing_extracts_csv_dates():
    days = parse_listing(LISTING_HTML)
    assert days == [date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)]


def test_parse_listing_deduplicates_and_sorts():
    html = '<a href="data_2026-08-27.csv">x</a><a href="data_2026-08-26.csv">y</a><a href="data_2026-08-27.csv">z</a>'
    assert parse_listing(html) == [date(2026, 8, 26), date(2026, 8, 27)]


def test_parse_listing_ignores_bad_dates():
    assert parse_listing('<a href="data_2026-13-99.csv">x</a>') == []


def test_day_from_filename():
    assert day_from_filename("data_2026-08-27.csv") == date(2026, 8, 27)
    assert day_from_filename("log_2022-11-20.txt") == date(2022, 11, 20)
    assert day_from_filename("other.txt") is None


def test_client_download_200_saves_file(tmp_path):
    client = HttpLogfileClient("192.168.10.65")
    day = date(2026, 8, 27)
    with mock.patch(
        "app.infrastructure.sources.http_logfile_client.urlopen"
    ) as urlopen:
        response = mock.MagicMock()
        response.read.return_value = b"row1\nrow2\n"
        urlopen.return_value.__enter__.return_value = response
        target = client.download(day, tmp_path)

    assert target is not None and target.name == "data_2026-08-27.csv"
    assert target.read_bytes() == b"row1\nrow2\n"


def test_client_download_404_returns_none(tmp_path):
    client = HttpLogfileClient("192.168.10.65")
    with mock.patch(
        "app.infrastructure.sources.http_logfile_client.urlopen",
        side_effect=__import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            "url", 404, "not found", None, None
        ),
    ):
        assert client.download(date(2026, 8, 27), tmp_path) is None


def test_client_download_raises_on_other_errors(tmp_path):
    from urllib.error import HTTPError

    client = HttpLogfileClient("192.168.10.65")
    with mock.patch(
        "app.infrastructure.sources.http_logfile_client.urlopen",
        side_effect=HTTPError("url", 500, "boom", None, None),
    ):
        try:
            client.download(date(2026, 8, 27), tmp_path)
            assert False, "expected HTTPError"
        except HTTPError:
            pass


def test_client_available_days_parses_listing():
    client = HttpLogfileClient("192.168.10.65")
    with mock.patch(
        "app.infrastructure.sources.http_logfile_client.urlopen"
    ) as urlopen:
        response = mock.MagicMock()
        response.read.return_value = LISTING_HTML.encode("utf-8")
        urlopen.return_value.__enter__.return_value = response
        days = client.available_days()

    assert days == [date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)]
