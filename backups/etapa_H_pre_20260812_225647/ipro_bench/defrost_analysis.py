from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean
from typing import Any

from .baseline import BaselineRepository, BaselineStatus, OperationalContext
from .field_diagnostics import BlackBoxStore, TimelineAnalyzer, TimelineKind


class DefrostPhase(StrEnum):
    PRE_DEFROST = "PRÉ-DEGELO"
    DEFROST = "DEGELO"
    DRIP = "GOTEJAMENTO"
    RETURN = "RETORNO À REFRIGERAÇÃO"
    RECOVERY = "RECUPERAÇÃO"
    POST_DEFROST = "PÓS-DEGELO"


class CycleStatus(StrEnum):
    COMPLETE = "COMPLETO"
    INCOMPLETE = "INCOMPLETO"
    INSUFFICIENT = "DADOS INSUFICIENTES"


class EvidenceLevel(StrEnum):
    OBSERVED_DIFFERENCE = "DIFERENÇA OBSERVADA"
    STATISTICAL_INDICATION = "INDICAÇÃO ESTATÍSTICA"
    SUFFICIENT_EVIDENCE = "EVIDÊNCIA SUFICIENTE"
    HYPOTHESIS = "HIPÓTESE"
    DIAGNOSIS = "DIAGNÓSTICO"


MARKERS = {
    "DEGELO_INICIO": "start_ns",
    "DEGELO_FIM": "end_ns",
    "GOTEJAMENTO_FIM": "drip_end_ns",
    "RETORNO_REFRIGERACAO": "return_ns",
    "RECUPERACAO": "recovery_ns",
}


@dataclass(frozen=True)
class PhaseWindow:
    phase: DefrostPhase
    start_ns: int
    end_ns: int
    duration_seconds: float
    evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class TemperatureSummary:
    variable_id: str
    before_average: float | None
    during_average: float | None
    after_average: float | None
    during_minimum: float | None
    during_maximum: float | None
    evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class DefrostCycle:
    id: str
    session_id: str
    sequence: int
    status: CycleStatus
    start_ns: int | None
    end_ns: int | None
    drip_end_ns: int | None
    return_ns: int | None
    recovery_ns: int | None
    duration_seconds: float | None
    recovery_seconds: float | None
    quality_score: float
    phases: tuple[PhaseWindow, ...]
    temperatures: tuple[TemperatureSummary, ...]
    state_events: tuple[dict[str, Any], ...]
    alarms: tuple[dict[str, Any], ...]
    first_deviation: dict[str, Any] | None
    evidence_ids: tuple[int, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class CycleDifference:
    metric: str
    current: float | str | None
    reference: float | str | None
    difference: float | None
    level: EvidenceLevel
    quality: str
    evidence_ids: tuple[int, ...]
    statement: str = "NÃO É DIAGNÓSTICO NEM CAUSA-RAIZ"


class DefrostCycleAnalyzer:
    PRE_SECONDS = 900
    POST_SECONDS = 1800

    def __init__(self, store: BlackBoxStore, baselines: BaselineRepository | None = None) -> None:
        self.store = store
        self.baselines = baselines

    def identify(self, session_id: str) -> list[DefrostCycle]:
        rows = self.store.query(session_id)
        starts = [row for row in rows if row["kind"] == TimelineKind.MARKER.value and row["name"].strip().upper() == "DEGELO_INICIO"]
        cycles = []
        for sequence, start in enumerate(starts, 1):
            next_start = starts[sequence]["timestamp_ns"] if sequence < len(starts) else None
            scope = [row for row in rows if row["timestamp_ns"] >= start["timestamp_ns"] and (next_start is None or row["timestamp_ns"] < next_start)]
            cycles.append(self._build(session_id, sequence, start, scope, rows))
        return cycles

    def _build(self, session_id: str, sequence: int, start: dict, scope: list[dict], all_rows: list[dict]) -> DefrostCycle:
        points: dict[str, int | None] = {field: None for field in MARKERS.values()}
        points["start_ns"] = start["timestamp_ns"]
        marker_ids = [start["id"]]
        for row in scope:
            if row["kind"] != TimelineKind.MARKER.value:
                continue
            field = MARKERS.get(row["name"].strip().upper())
            if field and points[field] is None:
                points[field] = row["timestamp_ns"]
                marker_ids.append(row["id"])
        missing = tuple(label for label, field in MARKERS.items() if points[field] is None)
        status = CycleStatus.COMPLETE if not missing else CycleStatus.INCOMPLETE
        start_ns, end_ns = points["start_ns"], points["end_ns"]
        duration = (end_ns-start_ns)/1e9 if end_ns is not None else None
        recovery = (points["recovery_ns"]-end_ns)/1e9 if end_ns is not None and points["recovery_ns"] is not None else None
        relevant_end = points["recovery_ns"] or points["return_ns"] or points["drip_end_ns"] or end_ns or start_ns
        evidence_rows = [r for r in all_rows if start_ns-self.PRE_SECONDS*1e9 <= r["timestamp_ns"] <= relevant_end+self.POST_SECONDS*1e9]
        samples = [r for r in evidence_rows if r["kind"] == TimelineKind.SAMPLE.value]
        usable = [r for r in samples if r["value"] is not None and r["quality"] == "VÁLIDA"]
        quality = len(usable)/len(samples) if samples else 0.0
        if not samples:
            status = CycleStatus.INSUFFICIENT
        phases = self._phases(points, marker_ids)
        temperatures = self._temperatures(samples, start_ns, end_ns, relevant_end)
        states = tuple(r for r in evidence_rows if r["kind"] == TimelineKind.STATE_CHANGE.value)
        alarms = tuple(r for r in evidence_rows if r["kind"] == TimelineKind.ALARM.value)
        first = next((r for r in evidence_rows if r["kind"] in (TimelineKind.DEVIATION.value, TimelineKind.ALARM.value, TimelineKind.COMMUNICATION_LOSS.value)), None)
        return DefrostCycle(f"{session_id}-DEG-{sequence:03d}", session_id, sequence, status,
            start_ns, end_ns, points["drip_end_ns"], points["return_ns"], points["recovery_ns"],
            duration, recovery, quality, tuple(phases), tuple(temperatures), states, alarms,
            first, tuple(r["id"] for r in evidence_rows), missing)

    def _phases(self, p: dict, marker_ids: list[int]) -> list[PhaseWindow]:
        spans = ((DefrostPhase.DEFROST,p["start_ns"],p["end_ns"]),
                 (DefrostPhase.DRIP,p["end_ns"],p["drip_end_ns"]),
                 (DefrostPhase.RETURN,p["drip_end_ns"],p["return_ns"]),
                 (DefrostPhase.RECOVERY,p["return_ns"],p["recovery_ns"]))
        return [PhaseWindow(phase,a,b,(b-a)/1e9,tuple(marker_ids)) for phase,a,b in spans if a is not None and b is not None and b >= a]

    def _temperatures(self, samples: list[dict], start: int, end: int | None, relevant_end: int) -> list[TemperatureSummary]:
        groups = {}
        for row in samples:
            evidence = row.get("evidence") or {}
            unit = evidence.get("unit", "")
            if unit in ("°C", "C") or "temp" in (row["variable_id"] or "").lower():
                groups.setdefault(row["variable_id"], []).append(row)
        output = []
        for variable, rows in groups.items():
            before = [float(r["value"]) for r in rows if r["timestamp_ns"] < start]
            during = [float(r["value"]) for r in rows if end is not None and start <= r["timestamp_ns"] <= end]
            after = [float(r["value"]) for r in rows if r["timestamp_ns"] > (end or relevant_end)]
            avg = lambda v: fmean(v) if v else None
            output.append(TemperatureSummary(variable,avg(before),avg(during),avg(after),min(during) if during else None,max(during) if during else None,tuple(r["id"] for r in rows)))
        return output

    def compare(self, current: DefrostCycle, reference: DefrostCycle) -> list[CycleDifference]:
        differences = []
        differences.append(self._difference("DURAÇÃO DO DEGELO",current.duration_seconds,reference.duration_seconds,current,reference))
        differences.append(self._difference("TEMPO DE RECUPERAÇÃO",current.recovery_seconds,reference.recovery_seconds,current,reference))
        current_t = {t.variable_id:t for t in current.temperatures}
        reference_t = {t.variable_id:t for t in reference.temperatures}
        for variable in sorted(current_t.keys() & reference_t.keys()):
            differences.append(self._difference(f"{variable} MÉDIA DURANTE",current_t[variable].during_average,reference_t[variable].during_average,current,reference))
        return differences

    def compare_baseline(self, cycle: DefrostCycle, baseline_id: str) -> list[CycleDifference]:
        if self.baselines is None: raise ValueError("Repositório de baseline indisponível.")
        baseline = self.baselines.get(baseline_id)
        if baseline.context is not OperationalContext.DEFROST: raise ValueError("Baseline não pertence ao contexto DEGELO.")
        if baseline.status not in (BaselineStatus.VALIDATED,BaselineStatus.ACTIVE): raise ValueError("Baseline deve estar VALIDADO ou ATIVO.")
        values = {t.variable_id:t.during_average for t in cycle.temperatures}
        result = []
        for profile in baseline.profiles:
            value = values.get(profile.variable_id)
            if value is None: continue
            outside = value < profile.normal_low or value > profile.normal_high
            if outside:
                delta = profile.normal_low-value if value<profile.normal_low else value-profile.normal_high
                result.append(CycleDifference(profile.variable_id,value,profile.average,abs(delta),EvidenceLevel.STATISTICAL_INDICATION,
                    "ADEQUADA" if cycle.quality_score>=.8 else "INADEQUADA",cycle.evidence_ids))
        return result

    @staticmethod
    def _difference(metric,current,reference,a,b):
        delta = current-reference if isinstance(current,(int,float)) and isinstance(reference,(int,float)) else None
        level = EvidenceLevel.OBSERVED_DIFFERENCE if delta is not None else EvidenceLevel.STATISTICAL_INDICATION
        return CycleDifference(metric,current,reference,delta,level,"ADEQUADA" if min(a.quality_score,b.quality_score)>=.8 else "INADEQUADA",tuple(dict.fromkeys(a.evidence_ids+b.evidence_ids)))
