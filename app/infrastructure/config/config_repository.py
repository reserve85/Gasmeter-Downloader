"""YAML-backed app settings with default merge and atomic writes.

The config file is the single, inspectable registry for user changes. Missing
keys are merged with defaults on load; writes go to a temp file + ``os.replace``
so a crash can never corrupt the config. Path keys are stored as absolute paths
resolved from the app base dir.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.domain.conversion import DEFAULT_CALORIFIC, DEFAULT_Z_VALUE

#: Runtime defaults applied when a key is missing or on first run (nested).
DEFAULTS: dict[str, Any] = {
    "app": {"language": "auto", "unit": "m³"},
    "device": {"ip": "192.168.10.65", "max_download_days": 30},
    "paths": {"download": "downloads", "archive": "archive", "database": "gasmeter.db"},
    "gas": {"default_calorific": float(DEFAULT_CALORIFIC), "default_z_value": float(DEFAULT_Z_VALUE)},
    "update": {"token": None},
    "charts": {"trend_horizon": 30},
    "window": {"width": 1100, "height": 720},
}

#: Flat dotted keys (used by the application layer).
DEFAULT_KEYS = [
    "app.language",
    "app.unit",
    "device.ip",
    "device.max_download_days",
    "paths.download",
    "paths.archive",
    "paths.database",
    "gas.default_calorific",
    "gas.default_z_value",
    "update.token",
    "charts.trend_horizon",
    "window.width",
    "window.height",
]


def _dot_get(data: dict, key: str, default: Any = None) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _dot_set(data: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


class YamlAppSettings:
    def __init__(self, config_path: str | Path, base: Path | None = None):
        self._config_path = Path(config_path)
        self._base = Path(base) if base else self._config_path.parent.parent
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        self._data = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
                self._data = loaded if isinstance(loaded, dict) else {}
            except (OSError, yaml.YAMLError):
                self._data = {}

    def _full_path(self, key: str) -> Path | None:
        value = _dot_get(self._data, key)
        if value is None:
            return None
        path = Path(str(value))
        return path if path.is_absolute() else (self._base / path)

    def get(self, key: str, default: Any = None) -> Any:
        fallback = default if default is not None else _dot_get(DEFAULTS, key)
        value = _dot_get(self._data, key, fallback)
        if key in ("paths.download", "paths.archive", "paths.database"):
            raw = _dot_get(self._data, key) or _dot_get(DEFAULTS, key)
            path = Path(str(raw))
            resolved = path if path.is_absolute() else (self._base / path).resolve()
            return str(resolved)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in ("paths.download", "paths.archive", "paths.database"):
            path = Path(str(value))
            value = str(path.resolve() if not path.is_absolute() else path)
        _dot_set(self._data, key, value)
        self._save()

    def _save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".app_config_", suffix=".tmp", dir=str(self._config_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(self._data, fh, allow_unicode=True, sort_keys=False)
            os.replace(tmp_name, self._config_path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    def to_dict(self) -> dict:
        return {key: self.get(key, None) for key in DEFAULT_KEYS}
