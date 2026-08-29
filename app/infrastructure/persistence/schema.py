"""SQLite schema + ``PRAGMA user_version`` migration bootstrap."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

DDL_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS meter_readings (
    day TEXT PRIMARY KEY,
    import_value REAL,
    interpolated_value REAL,
    adjusted_value REAL NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gas_parameters (
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    calorific_value REAL NOT NULL,
    z_value REAL NOT NULL,
    PRIMARY KEY (valid_from, valid_to)
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and stamp the user_version (idempotent)."""
    conn.executescript(DDL_SCHEMA_V1)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
