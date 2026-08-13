from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterable

from .field_diagnostics import BlackBoxStore, SessionStatus, TimelineKind


class OperationalContext(StrEnum):
    NORMAL = "OPERAÇÃO NORMAL"
    STARTUP = "PARTIDA"
    DEFROST = "DEGELO"
    POST_DEFROST = "PÓS-DEGELO"
    RECOVERY = "RECUPERAÇÃO"


class BaselineStatus(StrEnum):
    CANDIDATE = "CANDIDATO"
    VALIDATED = "VALIDADO"
    ACTIVE = "ATIVO"
    REJECTED = "REJEITADO"
    ARCHIVED = "ARQUIVADO"


@dataclass(frozen=True)
class SessionAssessment:
    session_id: str
    valid: bool
    quality_score: float
    sample_count: int
    usable_samples: int
    alarms: int
    communication_losses: int
    deviations: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class VariableProfile:
    variable_id: str
    name: str
    unit: str
    count: int
    average: float
    minimum: float
    maximum: float
    dispersion: float
    normal_low: float
    normal_high: float
    trend_per_second: float | None
    duration_seconds: float
    quality_score: float
    evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class BaselineVersion:
    id: str
    controller_id: str
    machine_id: str
    context: OperationalContext
    version: int
    status: BaselineStatus
    session_ids: tuple[str, ...]
    profiles: tuple[VariableProfile, ...]
    quality_score: float
    created_at: str
    period_start: str
    period_end: str
    reviewer: str = ""
    notes: str = ""


@dataclass(frozen=True)
class DeviationEvidence:
    variable_id: str
    magnitude: float
    duration_seconds: float
    first_timestamp: str
    context: OperationalContext
    quality: str
    classification: str
    conclusion: str
    evidence_ids: tuple[int, ...]


class BaselineRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self):
        with self._connect() as connection:
            connection.executescript("""
              CREATE TABLE IF NOT EXISTS baselines (
                id TEXT PRIMARY KEY, controller_id TEXT NOT NULL, machine_id TEXT NOT NULL,
                context TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
                session_ids_json TEXT NOT NULL, profiles_json TEXT NOT NULL,
                quality_score REAL NOT NULL, created_at TEXT NOT NULL,
                period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                reviewer TEXT NOT NULL, notes TEXT NOT NULL,
                UNIQUE(controller_id, machine_id, context, version));
              CREATE INDEX IF NOT EXISTS idx_baseline_lookup
                ON baselines(controller_id, machine_id, context, status, version);
              CREATE TABLE IF NOT EXISTS baseline_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, baseline_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                notes TEXT NOT NULL);
            """)

    def save(self, baseline: BaselineVersion, action: str, actor: str = "", notes: str = "") -> None:
        profiles = [asdict(profile) for profile in baseline.profiles]
        with self._connect() as connection:
            connection.execute("""INSERT INTO baselines VALUES
              (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                baseline.id, baseline.controller_id, baseline.machine_id,
                baseline.context.value, baseline.version, baseline.status.value,
                json.dumps(baseline.session_ids), json.dumps(profiles, ensure_ascii=False),
                baseline.quality_score, baseline.created_at, baseline.period_start,
                baseline.period_end, baseline.reviewer, baseline.notes))
            connection.execute("INSERT INTO baseline_audit(baseline_id,timestamp,action,actor,notes) VALUES(?,?,?,?,?)",
                (baseline.id, datetime.now().astimezone().isoformat(), action, actor, notes))

    def get(self, baseline_id: str) -> BaselineVersion:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM baselines WHERE id=?", (baseline_id,)).fetchone()
        if row is None:
            raise KeyError(baseline_id)
        return self._decode(row)

    def list(self, controller_id: str | None = None) -> list[BaselineVersion]:
        sql, params = "SELECT * FROM baselines", []
        if controller_id:
            sql += " WHERE controller_id=?"
            params.append(controller_id)
        sql += " ORDER BY created_at DESC"
        with self._connect() as connection:
            return [self._decode(row) for row in connection.execute(sql, params).fetchall()]

    def next_version(self, controller_id: str, machine_id: str, context: OperationalContext) -> int:
        with self._connect() as connection:
            value = connection.execute("SELECT MAX(version) FROM baselines WHERE controller_id=? AND machine_id=? AND context=?",
                (controller_id, machine_id, context.value)).fetchone()[0]
        return int(value or 0) + 1

    def transition(self, baseline_id: str, target: BaselineStatus, actor: str, notes: str = "") -> BaselineVersion:
        current = self.get(baseline_id)
        allowed = {
            BaselineStatus.CANDIDATE: {BaselineStatus.VALIDATED, BaselineStatus.REJECTED},
            BaselineStatus.VALIDATED: {BaselineStatus.ACTIVE, BaselineStatus.ARCHIVED},
            BaselineStatus.ACTIVE: {BaselineStatus.ARCHIVED},
            BaselineStatus.REJECTED: {BaselineStatus.ARCHIVED},
            BaselineStatus.ARCHIVED: set(),
        }
        if target not in allowed[current.status]:
            raise ValueError(f"Transição inválida: {current.status.value} -> {target.value}")
        if target is BaselineStatus.ACTIVE:
            with self._connect() as connection:
                active = connection.execute("SELECT id FROM baselines WHERE controller_id=? AND machine_id=? AND context=? AND status=? AND id<>?",
                    (current.controller_id, current.machine_id, current.context.value, BaselineStatus.ACTIVE.value, baseline_id)).fetchone()
            if active:
                raise ValueError("Arquive o baseline ativo antes de substituí-lo.")
        with self._connect() as connection:
            connection.execute("UPDATE baselines SET status=?, reviewer=?, notes=? WHERE id=?",
                (target.value, actor, notes, baseline_id))
            connection.execute("INSERT INTO baseline_audit(baseline_id,timestamp,action,actor,notes) VALUES(?,?,?,?,?)",
                (baseline_id, datetime.now().astimezone().isoformat(), target.value, actor, notes))
        return self.get(baseline_id)

    def active(self, controller_id: str, machine_id: str, context: OperationalContext) -> BaselineVersion | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM baselines WHERE controller_id=? AND machine_id=? AND context=? AND status=? ORDER BY version DESC LIMIT 1",
                (controller_id, machine_id, context.value, BaselineStatus.ACTIVE.value)).fetchone()
        return self._decode(row) if row else None

    @staticmethod
    def _decode(row) -> BaselineVersion:
        data = dict(row)
        data["context"] = OperationalContext(data["context"])
        data["status"] = BaselineStatus(data["status"])
        data["session_ids"] = tuple(json.loads(data.pop("session_ids_json")))
        data["profiles"] = tuple(VariableProfile(**{**item, "evidence_ids": tuple(item["evidence_ids"])}) for item in json.loads(data.pop("profiles_json")))
        return BaselineVersion(**data)


class BaselineService:
    MIN_USABLE_SAMPLES = 3

    def __init__(self, blackbox: BlackBoxStore, repository: BaselineRepository) -> None:
        self.blackbox, self.repository = blackbox, repository

    def assess_session(self, session_id: str) -> SessionAssessment:
        session = self.blackbox.get_session(session_id)
        rows = self.blackbox.query(session_id)
        samples = [r for r in rows if r["kind"] == TimelineKind.SAMPLE.value]
        usable = [r for r in samples if isinstance(r["value"], (int, float)) and r["quality"] == "VÁLIDA"]
        alarms = sum(r["kind"] == TimelineKind.ALARM.value and bool(r["value"]) for r in rows)
        losses = sum(r["kind"] == TimelineKind.COMMUNICATION_LOSS.value for r in rows)
        deviations = sum(r["kind"] == TimelineKind.DEVIATION.value for r in rows)
        reasons = []
        if session.status is not SessionStatus.FINISHED: reasons.append("SESSÃO NÃO FINALIZADA")
        if len(usable) < self.MIN_USABLE_SAMPLES: reasons.append("DADOS INSUFICIENTES")
        if alarms: reasons.append("ALARMES RELEVANTES")
        if losses: reasons.append("PERDA DE COMUNICAÇÃO")
        if deviations: reasons.append("COMPORTAMENTO ANORMAL MARCADO")
        score = len(usable) / len(samples) if samples else 0.0
        if score < .8: reasons.append("QUALIDADE INADEQUADA")
        return SessionAssessment(session_id, not reasons, score, len(samples), len(usable), alarms, losses, deviations, tuple(reasons))

    def create_candidate(self, controller_id: str, machine_id: str, context: OperationalContext,
                         session_ids: Iterable[str], notes: str = "") -> BaselineVersion:
        session_ids = tuple(dict.fromkeys(session_ids))
        if not session_ids:
            raise ValueError("DADOS INSUFICIENTES: nenhuma sessão selecionada.")
        assessments = [self.assess_session(sid) for sid in session_ids]
        invalid = [a for a in assessments if not a.valid]
        if invalid:
            details = "; ".join(f"{a.session_id}: {', '.join(a.reasons)}" for a in invalid)
            raise ValueError(f"Sessões inadequadas excluídas: {details}")
        sessions = [self.blackbox.get_session(sid) for sid in session_ids]
        if any(s.controller_id != controller_id for s in sessions):
            raise ValueError("Sessão pertence a controlador diferente.")
        profiles = self._profiles(session_ids)
        if not profiles:
            raise ValueError("DADOS INSUFICIENTES: nenhuma variável numérica válida.")
        now = datetime.now().astimezone().isoformat()
        baseline = BaselineVersion(
            f"BAS-{uuid.uuid4().hex[:12].upper()}", controller_id, machine_id, context,
            self.repository.next_version(controller_id, machine_id, context), BaselineStatus.CANDIDATE,
            session_ids, tuple(profiles), fmean(a.quality_score for a in assessments), now,
            min(s.started_at for s in sessions), max(s.ended_at or s.started_at for s in sessions), notes=notes,
        )
        self.repository.save(baseline, "CANDIDATO CRIADO", notes=notes)
        return baseline

    def _profiles(self, session_ids: tuple[str, ...]) -> list[VariableProfile]:
        groups: dict[str, list[dict]] = {}
        for session_id in session_ids:
            for row in self.blackbox.query(session_id, kinds=(TimelineKind.SAMPLE,)):
                if isinstance(row["value"], (int, float)) and row["quality"] == "VÁLIDA":
                    groups.setdefault(row["variable_id"], []).append(row)
        profiles = []
        for variable_id, rows in sorted(groups.items()):
            values = [float(row["value"]) for row in rows]
            if len(values) < self.MIN_USABLE_SAMPLES:
                continue
            dispersion = pstdev(values)
            times = [row["timestamp_ns"] for row in rows]
            duration = max(0.0, (max(times)-min(times))/1e9)
            trend = None if duration == 0 else (values[-1]-values[0])/duration
            first_evidence = rows[0].get("evidence") or {}
            profiles.append(VariableProfile(variable_id, rows[0]["name"], first_evidence.get("unit", ""),
                len(values), fmean(values), min(values), max(values), dispersion,
                fmean(values)-2*dispersion, fmean(values)+2*dispersion, trend, duration, 1.0,
                tuple(row["id"] for row in rows)))
        return profiles

    def compare(self, session_id: str, baseline_id: str) -> list[DeviationEvidence]:
        baseline = self.repository.get(baseline_id)
        if baseline.status not in (BaselineStatus.VALIDATED, BaselineStatus.ACTIVE):
            raise ValueError("Comparação exige baseline VALIDADO ou ATIVO.")
        assessment = self.assess_session(session_id)
        if assessment.usable_samples == 0:
            raise ValueError("DADOS INSUFICIENTES")
        deviations = []
        for profile in baseline.profiles:
            rows = [r for r in self.blackbox.query(session_id, variable_id=profile.variable_id, kinds=(TimelineKind.SAMPLE,)) if isinstance(r["value"], (int,float)) and r["quality"] == "VÁLIDA"]
            outside = [r for r in rows if float(r["value"]) < profile.normal_low or float(r["value"]) > profile.normal_high]
            if not outside: continue
            magnitudes = [profile.normal_low-float(r["value"]) if float(r["value"]) < profile.normal_low else float(r["value"])-profile.normal_high for r in outside]
            duration = (outside[-1]["timestamp_ns"]-outside[0]["timestamp_ns"])/1e9 if len(outside)>1 else 0.0
            sufficient = len(outside) >= 3 and assessment.quality_score >= .8
            deviations.append(DeviationEvidence(profile.variable_id, max(magnitudes), duration,
                outside[0]["timestamp"], baseline.context, "ADEQUADA" if assessment.quality_score >= .8 else "INADEQUADA",
                "EVIDÊNCIA SUFICIENTE" if sufficient else "INDICAÇÃO ESTATÍSTICA",
                "DESVIO OBSERVADO; NÃO É DIAGNÓSTICO NEM CAUSA-RAIZ", tuple(r["id"] for r in outside)))
        return deviations
