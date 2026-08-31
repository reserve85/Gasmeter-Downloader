"""Adapter tests: thin delegation to the shared github_updater package (v1.2.0).

The adapter must map the typed v1.2.0 API (``UpdateCheckResult.as_dict()``,
``DownloadResult.path``, raising ``UpdateError``) back onto the app's
``UpdatePort`` contract and guard the exe swap in dev mode.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from github_updater import DownloadResult, UpdateCheckResult, UpdateError

from app.infrastructure.updating.update_adapter import GithubUpdateAdapter


def _patch_service(fake_service):
    return mock.patch(
        "app.infrastructure.updating.update_adapter._build_service",
        return_value=fake_service,
    )


def test_check_delegates_and_returns_dict():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    fake.check_for_update.return_value = UpdateCheckResult(
        has_update=True, latest_version="2.0.0", download_url="u"
    )
    with _patch_service(fake):
        result = adapter.check("ghp_x")
    assert result == {
        "has_update": True,
        "latest_version": "2.0.0",
        "download_url": "u",
        "release_notes": "",
        "error": "",
    }
    fake.check_for_update.assert_called_once_with(token="ghp_x")


def test_check_empty_token_passed_through():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    fake.check_for_update.return_value = UpdateCheckResult()
    with _patch_service(fake):
        adapter.check("")
    fake.check_for_update.assert_called_once_with(token="")


def test_download_delegates_and_returns_path():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    fake.download_update.return_value = DownloadResult(path="C:\\tmp\\a.exe")
    with _patch_service(fake):
        path = adapter.download("http://x", "", None)
    assert path == "C:\\tmp\\a.exe"
    fake.download_update.assert_called_once_with(
        "http://x", token="", progress_callback=None
    )


def test_apply_guard_in_dev_mode():
    adapter = GithubUpdateAdapter()
    with mock.patch.object(sys, "frozen", False, create=True):
        with pytest.raises(RuntimeError, match="packaged"):
            adapter.apply("/tmp/a.exe")


def test_apply_delegates():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    fake.apply_update.return_value = True
    with (
        mock.patch.object(sys, "frozen", True, create=True),
        _patch_service(fake),
    ):
        ok = adapter.apply("/tmp/a.exe")
    assert ok is True
    fake.apply_update.assert_called_once_with("/tmp/a.exe")


def test_apply_propagates_update_error():
    """The package raises UpdateError on any preventable apply failure."""
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    fake.apply_update.side_effect = UpdateError("not writable")
    with (
        mock.patch.object(sys, "frozen", True, create=True),
        _patch_service(fake),
    ):
        with pytest.raises(UpdateError, match="not writable"):
            adapter.apply("/tmp/a.exe")


def test_restart_delegates():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    with _patch_service(fake):
        adapter.restart()
    fake.restart_app.assert_called_once()


def test_clean_old_files_noop_in_dev():
    """In dev mode cleanup must NOT touch anything (no package service)."""
    adapter = GithubUpdateAdapter()
    with mock.patch.object(sys, "frozen", False, create=True):
        adapter.clean_old_files()  # no exception, no service built


def test_clean_old_files_delegates_when_frozen():
    adapter = GithubUpdateAdapter()
    fake = mock.MagicMock()
    with (
        mock.patch.object(sys, "frozen", True, create=True),
        _patch_service(fake),
    ):
        adapter.clean_old_files()
    fake.clean_old_files.assert_called_once()
