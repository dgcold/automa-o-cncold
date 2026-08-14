from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from .telemetry import TelemetrySample


def high_resolution_timestamp() -> tuple[str, int]:
    timestamp_ns = time.time_ns()
    iso = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, timezone.utc).astimezone().isoformat(timespec="microseconds")
    return iso, timestamp_ns


class SessionStatus(StrEnum):
    ACTIVE = "ATIVA"
    FINISHED = "FINALIZADA"


class TimelineKind(StrEnum):
    SAMPLE = "AMOSTRA"
    STATE_CHANGE = "MUDANÇA DE ESTADO"
    ALARM = "ALARME"
    COMMUNICATION_LOSS = "PERDA DE COMUNICAÇÃO"
    COMMUNICATION_RESTORED = "COMUNICAÇÃO RESTABELECIDA"
    QUALITY_CHANGE = "MUDANÇA DE QUALIDADE"
    MARKER = "MARCADOR"
    DEVIATION = "DESVIO"
    RECOVERY = "RECUPERAÇÃO"


@dataclass(frozen=True)
class TimelineRecord:
    kind: TimelineKind
    timestamp: str
    timestamp_ns: int
    variable_id: str | None = None
    name: str = ""
    value: Any = None
    previous_value: Any = None
    quality: str = ""
    severity: str = "INFO"
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosticSession:
    id: str
    controller_id: str
    name: str
    status: SessionStatus
    started_at: str
    started_ns: int
    ended_at: str | None = None
    ended_ns: int | None = None
    notes: str = ""


class BlackBoxStore:
    """Append-only session database for normalized field observations."""

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
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS diagnostic_sessions (
                    id TEXT PRIMARY KEY, controller_id TEXT NOT NULL, name TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, started_ns INTEGER NOT NULL,
                    ended_at TEXT, ended_ns INTEGER, notes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS timeline_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, timestamp TEXT NOT NULL, timestamp_ns INTEGER NOT NULL,
                    variable_id TEXT, name TEXT NOT NULL, value_json TEXT,
                    previous_value_json TEXT, quality TEXT NOT NULL, severity TEXT NOT NULL,
                    message TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES diagnostic_sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_timeline_session_time
                    ON timeline_records(session_id, timestamp_ns, id);
                CREATE INDEX IF NOT EXISTS idx_timeline_variable
                    ON timeline_records(session_id, variable_id, timestamp_ns);
            """)

    def create_session(self, controller_id: str, name: str, notes: str = "") -> DiagnosticSession:
        timestamp, timestamp_ns = high_resolution_timestamp()
        session = DiagnosticSession(f"DIA-{uuid.uuid4().hex[:12].upper()}", controller_id, name, SessionStatus.ACTIVE, timestamp, timestamp_ns, notes=notes)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO diagnostic_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session.id, session.controller_id, session.name, session.status.value,
                 session.started_at, session.started_ns, None, None, session.notes),
            )
        return session

    def finish_session(self, session_id: str) -> DiagnosticSession:
        session = self.get_session(session_id)
        if session.status is not SessionStatus.ACTIVE:
            raise ValueError("Sessão já finalizada.")
        ended_at, ended_ns = high_resolution_timestamp()
        with self._connect() as connection:
            connection.execute(
                "UPDATE diagnostic_sessions SET status=?, ended_at=?, ended_ns=? WHERE id=?",
                (SessionStatus.FINISHED.value, ended_at, ended_ns, session_id),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> DiagnosticSession:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM diagnostic_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        data = dict(row)
        data["status"] = SessionStatus(data["status"])
        return DiagnosticSession(**data)

    def resolve_session_id(self, identifier: str) -> str:
        """Accept DIA directly or resolve an EXE recorded in the session notes."""
        value=identifier.strip()
        if not value:raise KeyError("Identificador de sessão vazio.")
        with self._connect() as connection:
            direct=connection.execute("SELECT id FROM diagnostic_sessions WHERE id=?",(value,)).fetchone()
            if direct:return str(direct["id"])
            rows=connection.execute("SELECT id,notes FROM diagnostic_sessions WHERE notes LIKE ? ORDER BY started_ns DESC",(f"%execution_id={value}%",)).fetchall()
        matches=[row["id"] for row in rows if any(part.strip()==f"execution_id={value}" for part in row["notes"].split(";"))]
        if len(matches)==1:return str(matches[0])
        if len(matches)>1:raise ValueError(f"Execução ambígua: {value}")
        raise KeyError(value)

    def sessions(self) -> list[DiagnosticSession]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM diagnostic_sessions ORDER BY started_ns DESC").fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["status"] = SessionStatus(data["status"])
            result.append(DiagnosticSession(**data))
        return result

    def append(self, session_id: str, record: TimelineRecord) -> int:
        if self.get_session(session_id).status is not SessionStatus.ACTIVE:
            raise ValueError("Não é permitido anexar dados a uma sessão finalizada.")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO timeline_records
                (session_id, kind, timestamp, timestamp_ns, variable_id, name,
                 value_json, previous_value_json, quality, severity, message, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, record.kind.value, record.timestamp, record.timestamp_ns,
                 record.variable_id, record.name, json.dumps(record.value, ensure_ascii=False),
                 json.dumps(record.previous_value, ensure_ascii=False), record.quality,
                 record.severity, record.message, json.dumps(record.evidence, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def append_many(self, session_id: str, records: Iterable[TimelineRecord]) -> int:
        """Persist an ordered telemetry batch in one atomic transaction."""
        if self.get_session(session_id).status is not SessionStatus.ACTIVE:
            raise ValueError("NÃ£o Ã© permitido anexar dados a uma sessÃ£o finalizada.")
        rows = [
            (
                session_id, record.kind.value, record.timestamp, record.timestamp_ns,
                record.variable_id, record.name,
                json.dumps(record.value, ensure_ascii=False),
                json.dumps(record.previous_value, ensure_ascii=False), record.quality,
                record.severity, record.message,
                json.dumps(record.evidence, ensure_ascii=False),
            )
            for record in records
        ]
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO timeline_records
                (session_id, kind, timestamp, timestamp_ns, variable_id, name,
                 value_json, previous_value_json, quality, severity, message, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        return len(rows)

    def query(self, session_id: str, *, variable_id: str | None = None,
              kinds: Iterable[TimelineKind] | None = None, start_ns: int | None = None,
              end_ns: int | None = None, limit: int = 5000) -> list[dict[str, Any]]:
        clauses, parameters = ["session_id=?"], [session_id]
        if variable_id:
            clauses.append("variable_id=?")
            parameters.append(variable_id)
        if kinds:
            values = [kind.value for kind in kinds]
            clauses.append(f"kind IN ({','.join('?' for _ in values)})")
            parameters.extend(values)
        if start_ns is not None:
            clauses.append("timestamp_ns>=?")
            parameters.append(start_ns)
        if end_ns is not None:
            clauses.append("timestamp_ns<=?")
            parameters.append(end_ns)
        parameters.append(max(1, int(limit)))
        sql = f"SELECT * FROM timeline_records WHERE {' AND '.join(clauses)} ORDER BY timestamp_ns, id LIMIT ?"
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["value"] = json.loads(item.pop("value_json"))
            item["previous_value"] = json.loads(item.pop("previous_value_json"))
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result


class BlackBoxRecorder:
    def __init__(self, store: BlackBoxStore) -> None:
        self.store = store
        self.session: DiagnosticSession | None = None
        self._last_values: dict[str, Any] = {}
        self._last_quality: dict[str, str] = {}
        self._communication_ok: bool | None = None

    def start(self, controller_id: str, name: str, notes: str = "") -> DiagnosticSession:
        if self.session and self.session.status is SessionStatus.ACTIVE:
            raise ValueError("Já existe uma sessão ativa.")
        self._last_values.clear()
        self._last_quality.clear()
        self._communication_ok = None
        self.session = self.store.create_session(controller_id, name, notes)
        return self.session

    def stop(self) -> DiagnosticSession:
        session_id = self._require_active()
        self.session = self.store.finish_session(session_id)
        return self.session

    def _require_active(self) -> str:
        if not self.session or self.session.status is not SessionStatus.ACTIVE:
            raise RuntimeError("Nenhuma sessão de diagnóstico ativa.")
        return self.session.id

    def ingest(self, samples: Iterable[TelemetrySample]) -> int:
        session_id = self._require_active()
        records: list[TimelineRecord] = []
        for sample in samples:
            timestamp_ns = self._ns_from_iso(sample.timestamp)
            record = TimelineRecord(TimelineKind.SAMPLE, sample.timestamp, timestamp_ns,
                sample.channel_id, sample.name, sample.value, quality=sample.quality.value,
                message=sample.display_value, evidence=sample.as_record())
            records.append(record)
            if sample.channel_id in self._last_values and self._last_values[sample.channel_id] != sample.value:
                records.append(TimelineRecord(
                    TimelineKind.STATE_CHANGE, sample.timestamp, timestamp_ns, sample.channel_id,
                    sample.name, sample.value, self._last_values[sample.channel_id],
                    sample.quality.value, message="Valor/estado alterado",
                    evidence={"source": sample.source, "connected": sample.connected},
                ))
            if sample.channel_id in self._last_quality and self._last_quality[sample.channel_id] != sample.quality.value:
                records.append(TimelineRecord(
                    TimelineKind.QUALITY_CHANGE, sample.timestamp, timestamp_ns, sample.channel_id,
                    sample.name, sample.quality.value, self._last_quality[sample.channel_id],
                    sample.quality.value, message="Qualidade alterada",
                ))
            self._last_values[sample.channel_id] = sample.value
            self._last_quality[sample.channel_id] = sample.quality.value
        return self.store.append_many(session_id, records)

    def communication(self, connected: bool, source: str, detail: str = "", timestamp: str | None = None) -> None:
        session_id = self._require_active()
        if self._communication_ok is connected:
            return
        timestamp = timestamp or high_resolution_timestamp()[0]
        timestamp_ns = self._ns_from_iso(timestamp)
        kind = TimelineKind.COMMUNICATION_RESTORED if connected else TimelineKind.COMMUNICATION_LOSS
        self.store.append(session_id, TimelineRecord(
            kind, timestamp, timestamp_ns, name=source,
            value=connected, previous_value=self._communication_ok,
            severity="INFO" if connected else "ALERTA", message=detail or kind.value,
        ))
        self._communication_ok = connected

    def alarm(self, alarm_id: str, active: bool, message: str, severity: str = "ALARME", timestamp: str | None = None) -> None:
        timestamp = timestamp or high_resolution_timestamp()[0]
        timestamp_ns = self._ns_from_iso(timestamp)
        self.store.append(self._require_active(), TimelineRecord(
            TimelineKind.ALARM, timestamp, timestamp_ns, alarm_id, alarm_id,
            active, severity=severity, message=message,
        ))

    def marker(self, label: str, notes: str = "", kind: TimelineKind = TimelineKind.MARKER, timestamp: str | None = None) -> None:
        timestamp = timestamp or high_resolution_timestamp()[0]
        timestamp_ns = self._ns_from_iso(timestamp)
        self.store.append(self._require_active(), TimelineRecord(
            kind, timestamp, timestamp_ns, name=label, message=notes or label,
        ))

    def deviation(self, variable_id: str, message: str, evidence: dict[str, Any] | None = None, timestamp: str | None = None) -> None:
        timestamp = timestamp or high_resolution_timestamp()[0]
        timestamp_ns = self._ns_from_iso(timestamp)
        self.store.append(self._require_active(), TimelineRecord(
            TimelineKind.DEVIATION, timestamp, timestamp_ns, variable_id, variable_id,
            severity="DESVIO", message=message, evidence=evidence or {},
        ))

    def recovery(self, message: str, evidence: dict[str, Any] | None = None, timestamp: str | None = None) -> None:
        timestamp = timestamp or high_resolution_timestamp()[0]
        timestamp_ns = self._ns_from_iso(timestamp)
        self.store.append(self._require_active(), TimelineRecord(
            TimelineKind.RECOVERY, timestamp, timestamp_ns, name="Recuperação",
            severity="INFO", message=message, evidence=evidence or {},
        ))

    @staticmethod
    def _ns_from_iso(value: str) -> int:
        return int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)


class TimelineAnalyzer:
    def __init__(self, store: BlackBoxStore) -> None:
        self.store = store

    def window(self, session_id: str, cursor_ns: int, before_seconds: float, after_seconds: float) -> list[dict]:
        return self.store.query(session_id, start_ns=cursor_ns-int(before_seconds*1e9), end_ns=cursor_ns+int(after_seconds*1e9))

    def first_deviation(self, session_id: str) -> dict | None:
        rows = self.store.query(session_id, kinds=(TimelineKind.DEVIATION, TimelineKind.ALARM, TimelineKind.COMMUNICATION_LOSS))
        return rows[0] if rows else None

    def duration_seconds(self, start: dict, end: dict) -> float:
        return max(0.0, (end["timestamp_ns"] - start["timestamp_ns"]) / 1_000_000_000)

    def correlation(self, session_id: str, variable_a: str, variable_b: str) -> dict[str, Any]:
        a = [row for row in self.store.query(session_id, variable_id=variable_a, kinds=(TimelineKind.SAMPLE,)) if isinstance(row["value"], (int, float))]
        b = [row for row in self.store.query(session_id, variable_id=variable_b, kinds=(TimelineKind.SAMPLE,)) if isinstance(row["value"], (int, float))]
        size = min(len(a), len(b))
        if size < 2:
            return {"coefficient": None, "pairs": size, "status": "DADOS INSUFICIENTES"}
        x, y = [float(row["value"]) for row in a[:size]], [float(row["value"]) for row in b[:size]]
        mx, my = sum(x)/size, sum(y)/size
        numerator = sum((vx-mx)*(vy-my) for vx, vy in zip(x, y))
        denominator = math.sqrt(sum((vx-mx)**2 for vx in x) * sum((vy-my)**2 for vy in y))
        coefficient = numerator/denominator if denominator else None
        return {"coefficient": coefficient, "pairs": size, "status": "CALCULADA" if coefficient is not None else "SEM VARIAÇÃO"}

    def summary(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        rows = self.store.query(session_id)
        first = self.first_deviation(session_id)
        last_recovery = next((row for row in reversed(rows) if row["kind"] in (TimelineKind.RECOVERY.value, TimelineKind.COMMUNICATION_RESTORED.value)), None)
        return {
            "session": asdict(session), "records": len(rows), "first_deviation": first,
            "recovered": last_recovery is not None,
            "evidence_ids": [row["id"] for row in rows],
        }
