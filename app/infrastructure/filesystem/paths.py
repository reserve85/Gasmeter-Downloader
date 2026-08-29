"""Filesystem paths: base dir (exe or repo root), defaults, ensure_dirs."""

from __future__ import annotations

import sys
from pathlib import Path

# this module lives at <root>/app/infrastructure/filesystem/paths.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # 4 levels up


def base_dir() -> Path:
    """Executable directory when frozen (PyInstaller), else the repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def default_dirs() -> dict[str, Path]:
    root = base_dir()
    return {
        "download": root / "downloads",
        "archive": root / "archive",
        "database": root / "gasmeter.db",
        "config": root / "config",
    }


def ensure_dirs(paths: dict[str, Path]) -> None:
    for key in ("download", "archive", "config"):
        paths[key].mkdir(parents=True, exist_ok=True)
