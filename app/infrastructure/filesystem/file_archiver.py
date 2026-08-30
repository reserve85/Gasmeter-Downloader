"""LogfileArchiver: move into the archive folder; never overwrite, never delete."""

from __future__ import annotations

import shutil
from pathlib import Path


class FileArchiver:
    def __init__(self, archive_dir: Path):
        self._archive_dir = Path(archive_dir)

    def set_archive_dir(self, archive_dir: Path) -> None:
        """Point the archiver at a new folder after a live settings change."""
        self._archive_dir = Path(archive_dir)

    def archive(self, path: Path) -> Path | None:
        """Move ``path`` into the archive folder.

        Collisions get a ``_1``, ``_2`` … suffix. A file that already lives in
        the archive folder is reported as-is (no move). Returns the final
        location, or None if the source vanished.
        """
        source = Path(path)
        if not source.exists():
            return None
        if source.resolve().parent == self._archive_dir.resolve():
            return source
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique_target(source.name)
        shutil.move(str(source), str(target))
        return target

    def is_archived(self, path: Path) -> bool:
        """True when the file already lives in the archive or a copy exists there."""
        p = Path(path)
        if p.resolve().parent == self._archive_dir.resolve():
            return True
        return (self._archive_dir / p.name).exists()

    def _unique_target(self, name: str) -> Path:
        candidate = self._archive_dir / name
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            candidate = self._archive_dir / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1
