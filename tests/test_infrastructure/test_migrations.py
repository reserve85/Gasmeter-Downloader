"""Migration tests: fresh bootstrap + version stamping."""

from __future__ import annotations

import sqlite3

from app.infrastructure.persistence.migrations import apply_migrations, current_version
from app.infrastructure.persistence.schema import SCHEMA_VERSION, DDL_SCHEMA_V1


def test_fresh_database_reaches_current_version(tmp_path):
    conn = sqlite3.connect(tmp_path / "m.db")
    version = apply_migrations(conn)
    assert version == SCHEMA_VERSION
    assert current_version(conn) == SCHEMA_VERSION
    conn.close()


def test_noop_when_up_to_date(tmp_path):
    conn = sqlite3.connect(tmp_path / "m.db")
    apply_migrations(conn)
    assert apply_migrations(conn) == SCHEMA_VERSION  # idempotent
    conn.close()


def test_tables_exist_after_migration(tmp_path):
    conn = sqlite3.connect(tmp_path / "m.db")
    apply_migrations(conn)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "meter_readings" in tables
    assert "gas_parameters" in tables
    conn.close()


def test_ddl_is_valid_sqlite(tmp_path):
    conn = sqlite3.connect(tmp_path / "m.db")
    conn.executescript(DDL_SCHEMA_V1)
    conn.commit()
    conn.close()
