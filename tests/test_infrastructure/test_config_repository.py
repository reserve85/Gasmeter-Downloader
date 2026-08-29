"""Config repository tests: default merge, atomic save, path resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.infrastructure.config.config_repository import DEFAULTS, YamlAppSettings


def test_defaults_on_first_run(tmp_path):
    config = tmp_path / "config" / "app_config.yaml"
    settings = YamlAppSettings(config, base=tmp_path)
    assert settings.get("device.ip") == "192.168.10.65"
    assert settings.get("device.max_download_days") == 30
    assert settings.get("gas.default_calorific") == 11.342
    assert settings.get("gas.default_z_value") == 0.9589


def test_get_unknown_key_returns_default(tmp_path):
    settings = YamlAppSettings(tmp_path / "config" / "app_config.yaml", base=tmp_path)
    assert settings.get("charts.trend_horizon", 99) == 99


def test_set_persists_atomically(tmp_path):
    config = tmp_path / "config" / "app_config.yaml"
    settings = YamlAppSettings(config, base=tmp_path)
    settings.set("device.max_download_days", 45)
    reloaded = YamlAppSettings(config, base=tmp_path)
    assert reloaded.get("device.max_download_days") == 45
    # file is valid YAML
    with open(config, "r", encoding="utf-8") as fh:
        assert isinstance(yaml.safe_load(fh), dict)


def test_path_keys_resolve_absolute(tmp_path):
    config = tmp_path / "config" / "app_config.yaml"
    settings = YamlAppSettings(config, base=tmp_path)
    assert Path(settings.get("paths.download")).is_absolute()


def test_missing_keys_merged_on_load(tmp_path):
    config = tmp_path / "config" / "app_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("device:\n  ip: 10.0.0.5\n", encoding="utf-8")
    settings = YamlAppSettings(config, base=tmp_path)
    assert settings.get("device.ip") == "10.0.0.5"
    assert settings.get("device.max_download_days") == DEFAULTS["device"]["max_download_days"]
