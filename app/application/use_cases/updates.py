"""Self-update use cases - thin delegation to the UpdatePort."""

from __future__ import annotations

from app.domain.entities import LogCategory, LogLevel


class CheckForUpdatesUseCase:
    def __init__(self, port, settings, logger, token_crypto=None):
        self._port = port
        self._settings = settings
        self._logger = logger
        self._crypto = token_crypto

    def run(self) -> dict:
        stored = self._settings.get("update.token") or ""
        if self._crypto is not None and stored:
            token = self._crypto.decrypt(str(stored)) or ""
        else:
            token = stored
        result = self._port.check(token)
        status = "update available" if result.get("has_update") else "up to date"
        if result.get("error"):
            self._logger.log(LogCategory.UPDATE, LogLevel.WARNING, f"Update check: {result['error']}")
        else:
            self._logger.log(
                LogCategory.UPDATE,
                LogLevel.INFO,
                f"Update check: latest={result.get('latest_version', '')} ({status})",
            )
        return result


class ApplyUpdateUseCase:
    def __init__(self, port, logger):
        self._port = port
        self._logger = logger

    def run(self, download_url: str, token: str = "") -> bool:
        self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Downloading update …")
        path = self._port.download(download_url, token, None)
        if not path:
            self._logger.log(LogCategory.UPDATE, LogLevel.ERROR, "Update download failed")
            return False
        self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Applying update …")
        applied = self._port.apply(path)
        if applied:
            self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Update applied; restarting app")
        else:
            self._logger.log(LogCategory.UPDATE, LogLevel.ERROR, "Update apply failed")
        return applied
