"""Update adapter tests: lazy import, dev-mode apply guard."""

from __future__ import annotations

import sys
from unittest import mock


def test_check_uses_github_updater():
    from app.infrastructure.updating.update_adapter import GithubUpdateAdapter

    adapter = GithubUpdateAdapter()
    fake_service = mock.MagicMock()
    fake_service.check_for_update.return_value = {"has_update": False}
    with mock.patch(
        "app.infrastructure.updating.update_adapter._build_service",
        return_value=fake_service,
    ):
        result = adapter.check("ghp_x")
    assert result == {"has_update": False}
    fake_service.check_for_update.assert_called_once_with(token="ghp_x")


def test_check_empty_token_passed_through():
    """The adapter must not block an anonymous public-repo check (fixed upstream)."""
    from app.infrastructure.updating.update_adapter import GithubUpdateAdapter

    adapter = GithubUpdateAdapter()
    fake_service = mock.MagicMock()
    fake_service.check_for_update.return_value = {"has_update": True, "latest_version": "9.9.9"}
    with mock.patch(
        "app.infrastructure.updating.update_adapter._build_service",
        return_value=fake_service,
    ):
        result = adapter.check("")
    assert result["has_update"] is True
    fake_service.check_for_update.assert_called_once_with(token="")


def test_download_delegates():
    from app.infrastructure.updating.update_adapter import GithubUpdateAdapter

    adapter = GithubUpdateAdapter()
    fake_service = mock.MagicMock()
    fake_service.download_update.return_value = "/tmp/a.exe"
    with mock.patch(
        "app.infrastructure.updating.update_adapter._build_service",
        return_value=fake_service,
    ):
        path = adapter.download("http://x", "", None)
    assert path == "/tmp/a.exe"


def test_apply_guard_in_dev_mode():
    from app.infrastructure.updating.update_adapter import GithubUpdateAdapter

    adapter = GithubUpdateAdapter()
    with mock.patch.object(sys, "frozen", False, create=True):
        try:
            adapter.apply("/tmp/a.exe")
            assert False, "expected RuntimeError in dev mode"
        except RuntimeError:
            pass
