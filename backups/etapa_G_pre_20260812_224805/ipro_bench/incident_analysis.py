from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean
from typing import Any, Iterable

from .baseline import BaselineService
from .field_diagnostics import BlackBoxStore, TimelineKind


class InvestigationLabel(StrEnum):
    EVENT = "EVENTO"
    FIRST_DEVIATION = "PRIMEIRO DESVIO"
    CORRELATION = "CORRELAÇÃO"
    EVIDENCE = "EVIDÊNCIA"
    HYPOTHESIS = "HIPÓTESE"
    DIAGNOSIS = "DIAGNÓSTICO"


class WindowPreset(StrEnum):
    SECONDS_30 = "30 SEGUNDOS"
    MINUTE_1 = "1 MINUTO"
    MINUTES_5 = "5 MINUTOS"
    MINUTES_15 = "15 MINUTOS"
    FULL_SESSION = "SESSÃO COMPLETA"

    @property
    def seconds(self) -> int | None:
        return {self.SECONDS_30:30,self.MINUTE_1:60,self.MINUTES_5:300,self.MINUTES_15:900,self.FULL_SESSION:None}[self]


@dataclass(frozen=True)
class InvestigationWindow:
    before: tuple[dict[str, Any], ...]
    during: tuple[dict[str, Any], ...]
    after: tuple[dict[str, Any], ...]
    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class EventInvestigation:
    session_id: str
    event: dict[str, Any]
    first_deviation: dict[str, Any] | None
    first_return: dict[str, Any] | None
    recovery: dict[str, Any] | None
    duration_seconds: float | None
    concurrent_events: tuple[dict[str, Any], ...]
    state_changes: tuple[dict[str, Any], ...]
    communication_events: tuple[dict[str, Any], ...]
    window: InvestigationWindow
    quality_score: float
    evidence_ids: tuple[int, ...]
    hypotheses: tuple[str, ...] = ("NÃO CONFIRMADAS",)
    diagnosis: str = "NÃO DETERMINADO"
    causality: str = "NÃO ESTABELECIDA"


@dataclass(frozen=True)
class EventComparison:
    event_key: str
    occurrences: int
    sessions: tuple[str, ...]
    average_duration_seconds: float | None
    quality_score: float
    common_preceding_variables: tuple[str, ...]
    temporal_offsets_seconds: tuple[float, ...]
    classification: str
    conclusion: str = "RECORRÊNCIA/CORRELAÇÃO; NÃO É CAUSALIDADE"


@dataclass(frozen=True)
class IntermittentFailure:
    event_key: str
    occurrences: int
    session_count: int
    first_seen: str
    last_seen: str
    intervals_seconds: tuple[float, ...]
    evidence_ids: tuple[int, ...]
    classification: str = "PADRÃO INTERMITENTE OBSERVADO"
    cause: str = "NÃO DETERMINADA"


class IncidentAnalyzer:
    CONCURRENT_NS = 1_000_000_000

    def __init__(self, store: BlackBoxStore, baselines: BaselineService | None = None) -> None:
        self.store, self.baselines = store, baselines

    def selectable_events(self, session_id: str) -> list[dict[str, Any]]:
        kinds = (TimelineKind.ALARM, TimelineKind.DEVIATION, TimelineKind.COMMUNICATION_LOSS,
                 TimelineKind.MARKER, TimelineKind.STATE_CHANGE)
        return self.store.query(session_id, kinds=kinds)

    def investigate(self, session_id: str, event_id: int, preset: WindowPreset = WindowPreset.MINUTES_5) -> EventInvestigation:
        all_rows = self.store.query(session_id)
        event = next((row for row in all_rows if row["id"] == int(event_id)), None)
        if event is None: raise KeyError(event_id)
        seconds = preset.seconds
        start_ns = all_rows[0]["timestamp_ns"] if seconds is None and all_rows else event["timestamp_ns"]-int((seconds or 0)*1e9)
        end_ns = all_rows[-1]["timestamp_ns"] if seconds is None and all_rows else event["timestamp_ns"]+int((seconds or 0)*1e9)
        rows = [r for r in all_rows if start_ns <= r["timestamp_ns"] <= end_ns]
        before = [r for r in rows if r["timestamp_ns"] < event["timestamp_ns"]]
        during = [r for r in rows if r["timestamp_ns"] == event["timestamp_ns"]]
        after = [r for r in rows if r["timestamp_ns"] > event["timestamp_ns"]]
        deviation_kinds = (TimelineKind.DEVIATION.value, TimelineKind.COMMUNICATION_LOSS.value)
        first_deviation = next((r for r in before if r["kind"] in deviation_kinds), None)
        recovery = next((r for r in after if r["kind"] in (TimelineKind.RECOVERY.value,TimelineKind.COMMUNICATION_RESTORED.value)), None)
        first_return = next((r for r in after if r["kind"] == TimelineKind.STATE_CHANGE.value and self._is_return(r)), recovery)
        duration = (recovery["timestamp_ns"]-event["timestamp_ns"])/1e9 if recovery else None
        concurrent = tuple(r for r in rows if r["id"] != event["id"] and abs(r["timestamp_ns"]-event["timestamp_ns"]) <= self.CONCURRENT_NS)
        states = tuple(r for r in rows if r["kind"] == TimelineKind.STATE_CHANGE.value)
        communication = tuple(r for r in rows if r["kind"] in (TimelineKind.COMMUNICATION_LOSS.value,TimelineKind.COMMUNICATION_RESTORED.value))
        samples = [r for r in rows if r["kind"] == TimelineKind.SAMPLE.value]
        valid = [r for r in samples if r["quality"] == "VÁLIDA" and r["value"] is not None]
        quality = len(valid)/len(samples) if samples else 0.0
        return EventInvestigation(session_id,event,first_deviation,first_return,recovery,duration,
            concurrent,states,communication,InvestigationWindow(tuple(before),tuple(during),tuple(after),start_ns,end_ns),
            quality,tuple(r["id"] for r in rows))

    def compare_events(self, occurrences: Iterable[tuple[str,int]], preset: WindowPreset = WindowPreset.MINUTES_5) -> EventComparison:
        investigations = [self.investigate(session,event,preset) for session,event in occurrences]
        if not investigations: raise ValueError("DADOS INSUFICIENTES")
        keys = [self._event_key(i.event) for i in investigations]
        if len(set(keys)) != 1: raise ValueError("Eventos selecionados não são semelhantes.")
        durations = [i.duration_seconds for i in investigations if i.duration_seconds is not None]
        preceding = []
        offsets = []
        for item in investigations:
            if item.first_deviation:
                if item.first_deviation["variable_id"]: preceding.append(item.first_deviation["variable_id"])
                offsets.append((item.event["timestamp_ns"]-item.first_deviation["timestamp_ns"])/1e9)
        common = tuple(sorted({v for v in preceding if preceding.count(v) == len(investigations)}))
        return EventComparison(keys[0],len(investigations),tuple(dict.fromkeys(i.session_id for i in investigations)),
            fmean(durations) if durations else None,fmean(i.quality_score for i in investigations),common,tuple(offsets),
            "RECORRÊNCIA COM PADRÃO COMUM" if common else "RECORRÊNCIA OBSERVADA")

    def intermittent_failures(self, session_ids: Iterable[str], minimum_occurrences: int = 2) -> list[IntermittentFailure]:
        groups: dict[str,list[tuple[str,dict]]] = {}
        for session_id in session_ids:
            for event in self.selectable_events(session_id):
                if event["kind"] not in (TimelineKind.ALARM.value,TimelineKind.COMMUNICATION_LOSS.value): continue
                groups.setdefault(self._event_key(event),[]).append((session_id,event))
        result=[]
        for key,items in groups.items():
            if len(items)<minimum_occurrences: continue
            ordered=sorted(items,key=lambda x:x[1]["timestamp_ns"])
            intervals=tuple((b[1]["timestamp_ns"]-a[1]["timestamp_ns"])/1e9 for a,b in zip(ordered,ordered[1:]))
            result.append(IntermittentFailure(key,len(items),len(set(s for s,_ in items)),ordered[0][1]["timestamp"],ordered[-1][1]["timestamp"],intervals,tuple(e["id"] for _,e in ordered)))
        return result

    def baseline_indications(self, session_id: str, baseline_id: str):
        if self.baselines is None: raise ValueError("Baseline indisponível.")
        return self.baselines.compare(session_id,baseline_id)

    @staticmethod
    def _event_key(event: dict) -> str:
        return f"{event['kind']}::{event['variable_id'] or event['name']}"

    @staticmethod
    def _is_return(row: dict) -> bool:
        return row["value"] in (True,"ON","LIGADO","NORMAL") or "retorno" in row["message"].lower()
