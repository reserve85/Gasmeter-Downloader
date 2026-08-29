"""HTTP logfile client for the AI-on-the-Edge device file server.

Base URL pattern: ``http://<ip>/fileserver/log/data/``. HTTP 404 means the day
is not available (returns None); other transport errors are raised so the sync
use case can report them as failures.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.infrastructure.sources.device_listing_parser import parse_listing

DEFAULT_LOG_PATH = "fileserver/log/data"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


class HttpLogfileClient:
    def __init__(
        self,
        device_ip: str,
        log_path: str = DEFAULT_LOG_PATH,
        connect_timeout: float = CONNECT_TIMEOUT,
        read_timeout: float = READ_TIMEOUT,
    ):
        self._base_url = f"http://{device_ip}/{log_path.lstrip('/')}/"
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout

    def _get(self, url: str) -> bytes | None:
        request = Request(url, headers={"User-Agent": "GasmeterDownloader/1.0"})
        try:
            with urlopen(request, timeout=self._read_timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        except URLError as exc:
            raise RuntimeError(f"Network error reaching device: {exc.reason}") from exc

    def available_days(self) -> list[date]:
        html = self._get(self._base_url)
        if html is None:
            raise RuntimeError("Device listing returned HTTP 404")
        text = html.decode("utf-8-sig", errors="replace")
        if "\ufffd" in text:
            text = html.decode("latin-1", errors="replace")
        return parse_listing(text)

    def download(self, day: date, target_dir: Path) -> Path | None:
        url = f"{self._base_url}data_{day.isoformat()}.csv"
        payload = self._get(url)
        if payload is None:
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"data_{day.isoformat()}.csv"
        target.write_bytes(payload)
        return target
