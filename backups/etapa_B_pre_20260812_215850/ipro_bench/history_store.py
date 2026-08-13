from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .telemetry import TelemetrySample


class PersistentHistory:
    """Append-only SQLite history for normalized telemetry."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    value REAL,
                    unit TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    source TEXT NOT NULL,
                    connected INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_samples_channel_time "
                "ON samples(channel_id, timestamp)"
            )

    def append(self, sample: TelemetrySample) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO samples
                (timestamp, channel_id, name, group_name, value, unit, quality,
                 source, connected, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sample.timestamp, sample.channel_id, sample.name, sample.group,
                    sample.value, sample.unit, sample.quality.value, sample.source,
                    int(sample.connected), json.dumps(sample.metadata, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def append_many(self, samples: Iterable[TelemetrySample]) -> int:
        return sum(1 for sample in samples if self.append(sample))

    def query(self, channel_id: str | None = None, limit: int = 1000) -> list[dict]:
        sql = "SELECT * FROM samples"
        parameters: list[object] = []
        if channel_id:
            sql += " WHERE channel_id = ?"
            parameters.append(channel_id)
        sql += " ORDER BY id DESC LIMIT ?"
        parameters.append(max(1, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in reversed(rows)]

    def statistics(self, channel_id: str) -> dict[str, float | int | None]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(value) AS count, AVG(value) AS average,
                MIN(value) AS minimum, MAX(value) AS maximum
                FROM samples WHERE channel_id = ? AND connected = 1""",
                (channel_id,),
            ).fetchone()
        return dict(row)

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
