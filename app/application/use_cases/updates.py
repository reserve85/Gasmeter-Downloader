"""Self-update use cases - thin delegation to the UpdatePort."""

from __future__ import annotations

from app.domain.entities import LogCategory, LogLevel
from app.infrastructure.config.security import TokenCrypto


class CheckForUpdatesUseCase:
    def __init__(self, port, settings, logger, token_crypto: TokenCrypto | None = None):
        self._port = port
        self._settings = settings
        self._logger = logger
        self._crypto = token_crypto or TokenCrypto()

    def run(self) -> dict:
        stored = self._settings.get("update.token") or ""
        token = self._crypto.decrypt(str(stored)) if stored else ""
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

    def run(self, download_url: str, token: str = "", progress_callback=None) -> bool:
        self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Downloading update …")
        path = self._port.download(download_url, token, progress_callback)
        if not path:
            self._logger.log(LogCategory.UPDATE, LogLevel.ERROR, "Update download failed")
            return False
        self._logger.log(LogCategory.UPDATE, LogLevel.INFO, "Applying update …")
        applied = self._port.apply(path)
        if applied:
            self._logger.log(
                LogCategory.UPDATE,
                LogLevel.INFO,
                "Update staged; the helper will swap the exe after the app exits.",
            )
        else:
            self._logger.log(LogCategory.UPDATE, LogLevel.ERROR, "Update apply failed")
        return applied
