"""Validation tests: intervals, values, IPs, settings schema."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import GasParameterInterval
from app.domain.validation import (
    parse_device_ip,
    validate_interval,
    validate_reading_value,
    validate_settings_changes,
)


def _interval(valid_from, valid_to, cal="11.342", z="0.9589"):
    return GasParameterInterval(
        valid_from=date.fromisoformat(valid_from),
        valid_to=date.fromisoformat(valid_to) if valid_to else None,
        calorific_value=Decimal(cal),
        z_value=Decimal(z),
    )


def test_valid_interval_has_no_errors():
    assert validate_interval(_interval("2026-01-01", "2026-12-31"), []) == []


def test_from_after_to():
    errors = validate_interval(_interval("2026-12-31", "2026-01-01"), [])
    assert any("after valid_to" in e for e in errors)


def test_non_positive_cal_or_z():
    errors = validate_interval(_interval("2026-01-01", None, cal="-1"), [])
    assert any("calorific_value" in e for e in errors)
    errors = validate_interval(_interval("2026-01-01", None, z="0"), [])
    assert any("z_value" in e for e in errors)


def test_overlap_rejected_inclusive_boundaries():
    existing = [_interval("2026-03-01", "2026-06-30")]
    assert validate_interval(_interval("2026-06-30", "2026-09-30"), existing) != []
    assert validate_interval(_interval("2026-07-01", "2026-09-30"), existing) == []


def test_overlap_with_open_ended():
    existing = [_interval("2026-03-01", None)]
    assert validate_interval(_interval("2026-06-01", "2026-06-30"), existing) != []


def test_reading_value_plausibility():
    assert validate_reading_value(Decimal("0"))
    assert validate_reading_value(Decimal("31163.63"))
    assert not validate_reading_value(Decimal("-1"))
    assert not validate_reading_value(Decimal("NaN"))
    assert not validate_reading_value(None)


def test_parse_device_ip():
    assert parse_device_ip("192.168.10.65") == "192.168.10.65"
    assert parse_device_ip(" 10.0.0.1 ") == "10.0.0.1"
    assert parse_device_ip("999.1.1.1") is None
    assert parse_device_ip("gasmeter") is None
    assert parse_device_ip("") is None


def test_settings_changes_ip_and_days():
    errors = validate_settings_changes({"device.ip": "not-an-ip"})
    assert "device.ip" in errors
    errors = validate_settings_changes({"device.max_download_days": 0})
    assert "device.max_download_days" in errors
    errors = validate_settings_changes({"device.max_download_days": 30})
    assert errors == {}
    errors = validate_settings_changes({"unknown.key": 1})
    assert "unknown.key" in errors
