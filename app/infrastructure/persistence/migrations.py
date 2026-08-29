"""Ordered, transactional schema migrations."""

from __future__ import annotations

import sqlite3

from app.infrastructure.persistence.schema import DDL_SCHEMA_V1

# Ordered list of (version, [sql statements]); version is the schema version
# the migration brings the database to.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [DDL_SCHEMA_V1]),
]


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations transactionally; returns final version."""
    version = current_version(conn)
    for target, statements in sorted(MIGRATIONS, key=lambda item: item[0]):
        if target <= version:
            continue
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.executescript(statement)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        version = target
    return version
