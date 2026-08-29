"""UpdatePort adapter wrapping ``github_updater.UpdateService``.

The shared ``github_updater`` package (Python_Units) is used **only** for the
application self-update. ``apply`` is guarded by ``sys.frozen`` so running from
source never attempts an exe replacement (dev mode -> False + INFO log).
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
        return service.check_for_update(token=token or "")

    def download(self, url: str, token: str, progress) -> str:
        service = _build_service()
        return service.download_update(url, token=token or "", progress_callback=progress) or ""

    def apply(self, path: str) -> bool:
        if not getattr(sys, "frozen", False):
            # Development mode: never attempt to replace the running exe.
            raise RuntimeError("Apply is only supported in the packaged build")
        service = _build_service()
        return bool(service.apply_update(path))

    def restart(self) -> None:
        service = _build_service()
        service.restart_app()

    def clean_old_files(self) -> None:
        """Remove leftover ``<exe>.old`` backups (no-op in dev / non-frozen)."""
        if not getattr(sys, "frozen", False):
            return
        try:
            from github_updater import UpdateService  # type: ignore[import-not-found]

            UpdateService.clean_old_files(sys.executable)
        except Exception:  # noqa: BLE001
            pass
