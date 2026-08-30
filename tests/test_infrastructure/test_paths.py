"""Paths tests: dev base dir, default layout, ensure_dirs."""

from __future__ import annotations

from unittest import mock

from app.infrastructure.filesystem.paths import (
    PROJECT_ROOT,
    base_dir,
    default_dirs,
    ensure_dirs,
    icon_path,
    resource_path,
)


def test_project_root_is_repo_root():
    assert PROJECT_ROOT.name == "Gasmeter-Downloader"
    assert (PROJECT_ROOT / "app").is_dir()
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_base_dir_dev_equals_project_root():
    with mock.patch("app.infrastructure.filesystem.paths.sys.frozen", False, create=True):
        assert base_dir() == PROJECT_ROOT


def test_base_dir_frozen_uses_exe_dir():
    fake_exe = PROJECT_ROOT / "dist" / "GasmeterDownloader.exe"
    with mock.patch("app.infrastructure.filesystem.paths.sys.frozen", True, create=True):
        with mock.patch("app.infrastructure.filesystem.paths.sys.executable", str(fake_exe)):
            assert base_dir() == fake_exe.parent


def test_default_dirs_layout():
    dirs = default_dirs()
    root = base_dir()
    assert dirs["download"] == root / "downloads"
    assert dirs["archive"] == root / "archive"
    assert dirs["database"] == root / "gasmeter.db"
    assert dirs["config"] == root / "config"


def test_ensure_dirs(tmp_path):
    dirs = {
        "download": tmp_path / "a",
        "archive": tmp_path / "b",
        "config": tmp_path / "config",
    }
    ensure_dirs(dirs)
    for path in dirs.values():
        assert path.is_dir()


def test_icon_path_points_to_existing_png():
    icon = icon_path()
    assert icon.name == "Icon.png"
    assert icon.exists()
    assert icon.suffix == ".png"


def test_resource_path_uses_meipass_when_frozen():
    fake = PROJECT_ROOT / "_MEIPASS"
    with mock.patch("app.infrastructure.filesystem.paths.sys._MEIPASS", str(fake), create=True):
        assert resource_path("Icon.png") == fake / "app" / "resources" / "Icon.png"
