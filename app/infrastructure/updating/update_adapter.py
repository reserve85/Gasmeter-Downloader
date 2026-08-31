"""UpdatePort adapter - thin delegation to the shared ``github_updater`` package.

All update logic (check / download / validate / stage / atomic swap / recovery)
lives in ``github_updater`` (reserve85/github_updater, pinned in requirements.txt).
This adapter only maps the typed v1.2.0 API back onto the app's ``UpdatePort``
contract and guards the exe replacement so running from source never attempts a
self-update.
"""

from __future__ import annotations

import sys


def _build_service():
    # Lazy import keeps the adapter importable even when the git dependency is
    # not installed (dev/test environments).
    from github_updater import UpdateService  # type: ignore[import-not-found]

    from app import __version__

    return UpdateService(
        current_version=__version__,
        owner="reserve85",
        repo="Gasmeter-Downloader",
        app_name="GasmeterDownloader",
    )


class GithubUpdateAdapter:
    def check(self, token: str) -> dict:
        service = _build_service()
        return service.check_for_update(token=token or "").as_dict()

    def download(self, url: str, token: str, progress) -> str:
        service = _build_service()
        return service.download_update(
            url, token=token or "", progress_callback=progress
        ).path

    def apply(self, path: str) -> bool:
        if not getattr(sys, "frozen", False):
            # Development mode: never attempt to replace the running exe.
            raise RuntimeError("Apply is only supported in the packaged build")
        # github_updater validates, stages and launches the safe swap; on any
        # preventable failure it raises UpdateError (shown in the dialog).
        service = _build_service()
        return bool(service.apply_update(path))

    def restart(self) -> None:
        service = _build_service()
        service.restart_app()

    def clean_old_files(self) -> None:
        """Restore a broken state and remove leftover stages (dev no-op)."""
        if not getattr(sys, "frozen", False):
            return
        service = _build_service()
        service.clean_old_files()
