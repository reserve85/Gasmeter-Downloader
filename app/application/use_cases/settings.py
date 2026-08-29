"""App settings use case - validated read/update/persist of the YAML config."""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import LogCategory, LogLevel
from app.domain.validation import validate_settings_changes


class SettingsUseCase:
    def __init__(self, settings, logger, token_crypto=None):
        self._settings = settings
        self._logger = logger
        self._crypto = token_crypto

    def get_all(self) -> dict:
        data = self._settings.to_dict()
        if self._crypto is not None and data.get("update.token"):
            decrypted = self._crypto.decrypt(str(data["update.token"]))
            data["update.token"] = decrypted or ""
        return data

    def update(self, changes: dict) -> dict:
        errors = validate_settings_changes(changes)
        if errors:
            summary = "; ".join(f"{k}: {', '.join(v)}" for k, v in errors.items())
            raise ValueError(f"Invalid settings: {summary}")
        for key, value in changes.items():
            if key == "device.max_download_days":
                value = int(value)
            elif key in ("gas.default_calorific", "gas.default_z_value"):
                value = Decimal(str(value))
            elif key == "update.token" and value and self._crypto is not None:
                value = self._crypto.encrypt(str(value))
            self._settings.set(key, value)
            self._logger.log(LogCategory.SETTINGS, LogLevel.INFO, f"Setting {key} = {'•••' if key == 'update.token' and value else value}")
        return self.get_all()
