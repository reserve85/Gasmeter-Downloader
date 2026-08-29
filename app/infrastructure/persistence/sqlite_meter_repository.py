"""MeterRepository on SQLite.

One connection per thread (UI thread + sync worker), WAL mode,
``busy_timeout``, Decimal <-> REAL round-trip via ``str``.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.domain.entities import DayReading, Source
from app.infrastructure.persistence.migrations import apply_migrations


def _to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class SqliteMeterRepository:
    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._local = threading.local()
        self._open_connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    # -- connection management -------------------------------------------------
    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            apply_migrations(conn)
            self._local.conn = conn
            with self._lock:
                self._open_connections.append(conn)
        return conn

    def close(self) -> None:
        with self._lock:
            for conn in self._open_connections:
                conn.close()
            self._open_connections.clear()

    # -- helpers ---------------------------------------------------------------
    def _row_to_reading(self, row: sqlite3.Row) -> DayReading:
        return DayReading(
            day=date.fromisoformat(row["day"]),
            import_value=_to_decimal(row["import_value"]),
            interpolated_value=_to_decimal(row["interpolated_value"]),
            adjusted_value=_to_decimal(row["adjusted_value"]) or Decimal("0"),
            source=Source(row["source"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    # -- MeterRepository port --------------------------------------------------
    def get_reading(self, day: date) -> DayReading | None:
        conn = self._connection()
        row = conn.execute("SELECT * FROM meter_readings WHERE day = ?", (day.isoformat(),)).fetchone()
        return self._row_to_reading(row) if row else None

    def get_readings(self, start: date | None, end: date | None) -> list[DayReading]:
        conn = self._connection()
        if start is None and end is None:
            rows = conn.execute("SELECT * FROM meter_readings ORDER BY day").fetchall()
        elif start is None:
            rows = conn.execute(
                "SELECT * FROM meter_readings WHERE day <= ? ORDER BY day", (end.isoformat(),)
            ).fetchall()
        elif end is None:
            rows = conn.execute(
                "SELECT * FROM meter_readings WHERE day >= ? ORDER BY day", (start.isoformat(),)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM meter_readings WHERE day >= ? AND day <= ? ORDER BY day",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._row_to_reading(r) for r in rows]

    def all_days_with_import(self) -> set[date]:
        conn = self._connection()
        rows = conn.execute("SELECT day FROM meter_readings WHERE import_value IS NOT NULL").fetchall()
        return {date.fromisoformat(r["day"]) for r in rows}

    def latest_reading_day(self) -> date | None:
        conn = self._connection()
        row = conn.execute("SELECT MAX(day) AS day FROM meter_readings").fetchone()
        return date.fromisoformat(row["day"]) if row and row["day"] else None

    def save_import(self, day: date, value: Decimal) -> None:
        """Import a logfile value.

        A day with a manual modification only gets its ``import_value``
        backfilled; ``adjusted_value`` + ``source`` stay untouched
        (modified > imported).
        """
        conn = self._connection()
        now = self._now()
        conn.execute(
            """
            INSERT INTO meter_readings (day, import_value, adjusted_value, source, updated_at)
            VALUES (?, ?, ?, 'logfile', ?)
            ON CONFLICT(day) DO UPDATE SET
                import_value   = excluded.import_value,
                adjusted_value = CASE
                    WHEN meter_readings.source = 'manual'
                        THEN meter_readings.adjusted_value
                    ELSE excluded.adjusted_value END,
                source         = CASE
                    WHEN meter_readings.source = 'manual'
                        THEN meter_readings.source
                    ELSE 'logfile' END,
                updated_at     = excluded.updated_at
            """,
            (day.isoformat(), str(value), str(value), now),
        )
        conn.commit()

    def save_interpolated(self, day: date, value: Decimal) -> None:
        """Store an interpolation on a free or previously interpolated day.

        Defensive: rows whose source is logfile/manual (i.e. have an import
        value) are never overwritten.
        """
        conn = self._connection()
        now = self._now()
        conn.execute(
            """
            INSERT INTO meter_readings (day, interpolated_value, adjusted_value, source, updated_at)
            VALUES (?, ?, ?, 'interpolated', ?)
            ON CONFLICT(day) DO UPDATE SET
                interpolated_value = excluded.interpolated_value,
                source             = CASE
                    WHEN meter_readings.import_value IS NULL
                        AND meter_readings.source NOT IN ('logfile', 'manual')
                        THEN excluded.source
                    ELSE meter_readings.source END,
                adjusted_value     = CASE
                    WHEN meter_readings.import_value IS NULL
                        AND meter_readings.source NOT IN ('logfile', 'manual')
                        THEN excluded.adjusted_value
                    ELSE meter_readings.adjusted_value END,
                updated_at         = excluded.updated_at
            """,
            (day.isoformat(), str(value), str(value), now),
        )
        conn.commit()

    def save_manual(self, day: date, value: Decimal) -> None:
        """Set the Modified (adjusted) value and force ``source = manual``."""
        conn = self._connection()
        now = self._now()
        conn.execute(
            """
            INSERT INTO meter_readings (day, adjusted_value, source, updated_at)
            VALUES (?, ?, 'manual', ?)
            ON CONFLICT(day) DO UPDATE SET
                adjusted_value = excluded.adjusted_value,
                source         = 'manual',
                updated_at     = excluded.updated_at
            """,
            (day.isoformat(), str(value), now),
        )
        conn.commit()

    def restore_to_original(self, day: date) -> None:
        """Trust hierarchy: adjusted <- import, else <- interpolated, else unchanged."""
        conn = self._connection()
        now = self._now()
        conn.execute(
            """
            UPDATE meter_readings SET
                adjusted_value = COALESCE(import_value, interpolated_value, adjusted_value),
                source         = CASE
                    WHEN import_value IS NOT NULL THEN 'logfile'
                    WHEN interpolated_value IS NOT NULL THEN 'interpolated'
                    ELSE source END,
                updated_at     = ?
            WHERE day = ?
            """,
            (now, day.isoformat()),
        )
        conn.commit()
