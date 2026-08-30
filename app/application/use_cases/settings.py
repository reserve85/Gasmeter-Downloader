"""App settings use case - validated read/update/persist of the YAML config."""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import LogCategory, LogLevel
from app.domain.validation import coerce_bool, validate_settings_changes
from app.infrastructure.config.security import TokenCrypto


class SettingsUseCase:
    def __init__(self, settings, logger, token_crypto: TokenCrypto | None = None):
        self._settings = settings
        self._logger = logger
        # The GitHub token must never end up in clear text: encryption is
        # mandatory, so a missing crypto falls back to the machine-derived one.
        self._crypto = token_crypto or TokenCrypto()

    def get_all(self) -> dict:
        data = self._settings.to_dict()
        if data.get("update.token"):
            data["update.token"] = self._crypto.decrypt(str(data["update.token"]))
        return data

    def update(self, changes: dict) -> dict:
        errors = validate_settings_changes(changes)
        if errors:
            summary = "; ".join(f"{k}: {', '.join(v)}" for k, v in errors.items())
            raise ValueError(f"Invalid settings: {summary}")
        for key, value in changes.items():
            if key == "device.max_download_days":
                value = int(value)
            elif key == "device.auto_fetch_on_startup":
                value = coerce_bool(value)
            elif key in ("gas.default_calorific", "gas.default_z_value"):
                value = Decimal(str(value))
            elif key == "update.token" and value:
                value = self._crypto.encrypt(str(value))
            self._settings.set(key, value)
            self._logger.log(LogCategory.SETTINGS, LogLevel.INFO, f"Setting {key} = {'•••' if key == 'update.token' and value else value}")
        return self.get_all()
