"""Validation helpers for gas intervals, readings, IPs and settings (pure)."""

from __future__ import annotations

import ipaddress
import re
from datetime import date
from decimal import Decimal
from math import isfinite
from typing import Any

from app.domain.entities import GasParameterInterval


def validate_interval(interval: GasParameterInterval, existing: list[GasParameterInterval]) -> list[str]:
    """Return human-readable validation errors (empty = valid).

    Rules: ``valid_from <= valid_to`` (or open-ended), non-positive
    calorific/z rejected, overlapping dates rejected (boundaries inclusive).
    """
    errors: list[str] = []
    if interval.calorific_value <= 0:
        errors.append("calorific_value must be > 0")
    if interval.z_value <= 0:
        errors.append("z_value must be > 0")
    if interval.valid_to is not None and interval.valid_from > interval.valid_to:
        errors.append("valid_from must not be after valid_to")
    for other in existing:
        if other is interval:
            continue
        if _overlaps(interval, other):
            errors.append(
                f"Overlap with existing interval "
                f"{other.valid_from:%Y-%m-%d} … {other.valid_to or 'open'}"
            )
    return errors


def _overlaps(a: GasParameterInterval, b: GasParameterInterval) -> bool:
    a_end = a.valid_to if a.valid_to is not None else date.max
    b_end = b.valid_to if b.valid_to is not None else date.max
    return a.valid_from <= b_end and b.valid_from <= a_end


def validate_reading_value(value: Decimal) -> bool:
    """A stored/entered meter value must be finite and >= 0."""
    if value is None:
        return False
    try:
        return isfinite(float(value)) and value >= 0
    except (ValueError, TypeError, OverflowError):
        return False


def validate_ascending_order(
    prev_value: Decimal | None,
    value: Decimal,
    next_value: Decimal | None,
) -> list[str]:
    """A corrected meter value must stay non-decreasing between its neighbors.

    The check is inclusive (a standing meter keeps equal readings valid).
    A missing neighbor imposes no constraint.
    """
    if not validate_reading_value(value):
        return ["Value must be a finite non-negative number"]
    errors: list[str] = []
    if prev_value is not None and value < prev_value:
        errors.append(f"Value must be >= previous day ({prev_value})")
    if next_value is not None and value > next_value:
        errors.append(f"Value must be <= next day ({next_value})")
    return errors


_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def parse_device_ip(value: str) -> str | None:
    """Strict IPv4; None on invalid."""
    try:
        ip = ipaddress.IPv4Address(value.strip())
    except (ValueError, AttributeError):
        return None
    return str(ip)


_SETTINGS_KEYS = {
    "app.language",
    "app.unit",
    "device.ip",
    "device.max_download_days",
    "device.auto_fetch_on_startup",
    "paths.download",
    "paths.archive",
    "paths.database",
    "gas.default_calorific",
    "gas.default_z_value",
    "update.token",
    "charts.trend_horizon",
    "theme.mode",
}

_THEME_MODES = ("auto", "dark", "light")
_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}


def coerce_bool(value: Any) -> bool:
    """Parse a boolean-ish settings value (bool, 'true'/'false', '1'/'0')."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _BOOL_TRUE:
            return True
        if text in _BOOL_FALSE:
            return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


def _is_bool(value: Any) -> bool:
    try:
        coerce_bool(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_settings_changes(changes: dict[str, Any]) -> dict[str, list[str]]:
    """Per-key validation errors for settings updates. Unknown keys are rejected."""
    errors: dict[str, list[str]] = {}
    for key, value in changes.items():
        if key not in _SETTINGS_KEYS:
            errors[key] = [f"Unknown setting key: {key}"]
            continue
        if key == "device.ip" and parse_device_ip(str(value)) is None:
            errors[key] = ["Invalid IPv4 address"]
        elif key == "device.max_download_days":
            try:
                n = int(value)
                if n < 1 or n > 3650:
                    raise ValueError
            except (TypeError, ValueError):
                errors[key] = ["Must be an integer between 1 and 3650"]
        elif key in ("gas.default_calorific", "gas.default_z_value"):
            try:
                if float(value) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors[key] = ["Must be a positive number"]
        elif key == "charts.trend_horizon":
            try:
                if int(value) < 1 or int(value) > 365:
                    raise ValueError
            except (TypeError, ValueError):
                errors[key] = ["Must be an integer between 1 and 365"]
        elif key == "theme.mode" and value not in _THEME_MODES:
            errors[key] = [f"Must be one of: {', '.join(_THEME_MODES)}"]
        elif key == "device.auto_fetch_on_startup" and not _is_bool(value):
            errors[key] = ["Must be a boolean"]
    return errors
