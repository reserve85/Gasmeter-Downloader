"""Archiver tests: move, collision suffixes, never delete."""

from __future__ import annotations


from app.infrastructure.filesystem.file_archiver import FileArchiver


def test_archive_moves_file(tmp_path):
    archive_dir = tmp_path / "archive"
    source = tmp_path / "data_2026-01-01.csv"
    source.write_text("x")
    archiver = FileArchiver(archive_dir)

    target = archiver.archive(source)

    assert target.parent == archive_dir
    assert target.exists()
    assert not source.exists()  # moved, never copied


def test_archive_collision_suffix(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "data_2026-01-01.csv").write_text("old")
    source = tmp_path / "data_2026-01-01.csv"
    source.write_text("new")
    archiver = FileArchiver(archive_dir)

    target = archiver.archive(source)

    assert target.name == "data_2026-01-01_1.csv"
    assert (archive_dir / "data_2026-01-01.csv").read_text() == "old"  # never overwritten


def test_archive_never_deletes_source_copy_on_collision(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "a.csv").write_text("1")
    (archive_dir / "a_1.csv").write_text("2")
    source = tmp_path / "a.csv"
    source.write_text("3")
    archiver = FileArchiver(archive_dir)
    target = archiver.archive(source)
    assert target.name == "a_2.csv"


def test_is_archived(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "a.csv").write_text("1")
    archiver = FileArchiver(archive_dir)
    assert archiver.is_archived(tmp_path / "a.csv")  # same name exists in archive
    assert not archiver.is_archived(tmp_path / "b.csv")
    inside = archive_dir / "c.csv"
    inside.write_text("1")
    assert archiver.is_archived(inside)


def test_archive_of_file_already_in_archive_is_noop(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    inside = archive_dir / "a.csv"
    inside.write_text("1")
    archiver = FileArchiver(archive_dir)
    result = archiver.archive(inside)
    assert result == inside


def test_archive_missing_source_returns_none(tmp_path):
    archiver = FileArchiver(tmp_path / "archive")
    assert archiver.archive(tmp_path / "missing.csv") is None
