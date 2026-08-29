"""GasParameterRepository on SQLite; overlap-aware lookups."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.entities import GasParameterInterval
from app.infrastructure.persistence.migrations import apply_migrations

import sqlite3


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


class SqliteGasParameterRepository:
    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            apply_migrations(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _row_to_interval(self, row: sqlite3.Row) -> GasParameterInterval:
        return GasParameterInterval(
            valid_from=date.fromisoformat(row["valid_from"]),
            valid_to=date.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
            calorific_value=_to_decimal(row["calorific_value"]),
            z_value=_to_decimal(row["z_value"]),
        )

    def all_intervals(self) -> list[GasParameterInterval]:
        conn = self._connection()
        rows = conn.execute("SELECT * FROM gas_parameters ORDER BY valid_from").fetchall()
        return [self._row_to_interval(r) for r in rows]

    def upsert_interval(self, interval: GasParameterInterval) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO gas_parameters
                (valid_from, valid_to, calorific_value, z_value)
            VALUES (?, ?, ?, ?)
            """,
            (
                interval.valid_from.isoformat(),
                interval.valid_to.isoformat() if interval.valid_to else None,
                str(interval.calorific_value),
                str(interval.z_value),
            ),
        )
        conn.commit()

    def delete_interval(self, valid_from: date, valid_to: date | None) -> None:
        conn = self._connection()
        conn.execute(
            "DELETE FROM gas_parameters WHERE valid_from = ? AND valid_to IS ?",
            (valid_from.isoformat(), valid_to.isoformat() if valid_to else None),
        )
        conn.commit()

    def parameter_for(self, day: date) -> GasParameterInterval | None:
        conn = self._connection()
        row = conn.execute(
            """
            SELECT * FROM gas_parameters
            WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to >= ?)
            ORDER BY valid_from DESC
            LIMIT 1
            """,
            (day.isoformat(), day.isoformat()),
        ).fetchone()
        return self._row_to_interval(row) if row else None
