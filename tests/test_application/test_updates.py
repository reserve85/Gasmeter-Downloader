"""Update use case tests (port mocked; mirrors the reference service tests)."""

from __future__ import annotations

from app.application.use_cases.updates import ApplyUpdateUseCase, CheckForUpdatesUseCase
from app.domain.entities import LogCategory

from tests.conftest import FakeSettings


class FakeUpdatePort:
    def __init__(self):
        self.check_result = {"has_update": False, "latest_version": "1.0.0", "download_url": "", "release_notes": "", "error": ""}
        self.download_result = "/tmp/update.exe"
        self.apply_result = True
        self.check_calls = 0
        self.restarts = 0
        self.progress_calls: list = []

    def check(self, token: str) -> dict:
        self.check_calls += 1
        return self.check_result

    def download(self, url: str, token: str, progress) -> str:
        self.progress_calls.append(progress)
        return self.download_result

    def apply(self, path: str) -> bool:
        return self.apply_result

    def restart(self) -> None:
        self.restarts += 1


def test_check_for_updates_up_to_date(logger):
    port = FakeUpdatePort()
    settings = FakeSettings({"update.token": ""})
    use_case = CheckForUpdatesUseCase(port, settings, logger)
    result = use_case.run()
    assert result["has_update"] is False
    assert logger.messages_of(LogCategory.UPDATE)


def test_check_for_updates_available(logger):
    port = FakeUpdatePort()
    port.check_result = {"has_update": True, "latest_version": "2.0.0", "download_url": "http://x/a.exe", "release_notes": "notes", "error": ""}
    use_case = CheckForUpdatesUseCase(port, FakeSettings(), logger)
    result = use_case.run()
    assert result["has_update"] is True
    assert result["latest_version"] == "2.0.0"


def test_check_error_logs_warning(logger):
    port = FakeUpdatePort()
    port.check_result = {"has_update": False, "latest_version": "", "download_url": "", "release_notes": "", "error": "No GitHub token configured"}
    use_case = CheckForUpdatesUseCase(port, FakeSettings(), logger)
    result = use_case.run()
    assert result["error"]
    warnings = [m for cat, lvl, m in logger.events if cat == LogCategory.UPDATE and "No GitHub token" in m]
    assert warnings


def test_apply_update_full_flow(logger):
    port = FakeUpdatePort()
    use_case = ApplyUpdateUseCase(port, logger)
    assert use_case.run("http://x/a.exe", token="") is True
    # The use case no longer calls restart — the batch helper swaps the exe
    # after the app exits naturally.  Verify it was NOT called.
    assert port.restarts == 0
    assert any("staged" in m for _, _, m in logger.events)


def test_apply_update_no_restart_after_staged(logger):
    """After staging, the use case does not kill the process."""
    port = FakeUpdatePort()
    use_case = ApplyUpdateUseCase(port, logger)
    assert use_case.run("http://x/a.exe", token="") is True
    assert port.restarts == 0


def test_apply_update_failed_download(logger):
    port = FakeUpdatePort()
    port.download_result = ""
    use_case = ApplyUpdateUseCase(port, logger)
    assert use_case.run("http://x/a.exe") is False


def test_apply_update_forwards_progress_callback(logger):
    port = FakeUpdatePort()
    use_case = ApplyUpdateUseCase(port, logger)
    callback = lambda downloaded, total: None  # noqa: E731
    assert use_case.run("http://x/a.exe", token="", progress_callback=callback) is True
    assert port.progress_calls == [callback]
