from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from .anomaly_analysis import AnomalyClass, AnomalyRepository, AnalysisState
from .defrost_analysis import CycleStatus, DefrostCycleAnalyzer
from .field_diagnostics import BlackBoxStore, TimelineKind


class HealthDimension(StrEnum):
    CONTROL = "CONTROLE"
    THERMAL = "TÉRMICA"
    DEFROST = "DEGELO"
    COMPRESSOR = "COMPRESSOR"
    ELECTRICAL = "ELÉTRICA"
    COMMUNICATION = "COMUNICAÇÃO"
    DATA = "SENSORES / DADOS"
    GENERAL = "GERAL"


class HealthClassification(StrEnum):
    NORMAL = "NORMAL"
    ATTENTION = "ATENÇÃO"
    BEHAVIOR_CHANGE = "ALTERAÇÃO DE COMPORTAMENTO"
    DEGRADATION_INDICATED = "DEGRADAÇÃO INDICADA"
    INSUFFICIENT = "DADOS INSUFICIENTES"
    UNDETERMINED = "NÃO DETERMINADO"
    NOT_CONNECTED = "NÃO CONECTADO / SEM DADOS"


class PeriodKind(StrEnum):
    SESSION = "SESSÃO"
    DAY = "DIA"
    WEEK = "SEMANA"
    MONTH = "MÊS"
    CUSTOM = "PERSONALIZADO"


@dataclass(frozen=True)
class TrendMetric:
    name: str
    values: tuple[float, ...]
    slope: float | None
    direction: str
    persistent: bool
    evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class HealthIndicator:
    dimension: HealthDimension
    score: float | None
    classification: HealthClassification
    quality_score: float
    reasons: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    explanation: str
    probability: str = "NÃO É PROBABILIDADE DE FALHA"


@dataclass(frozen=True)
class OperationalSignature:
    id: str
    session_id: str
    variables: tuple[str, ...]
    feature_names: tuple[str, ...]
    features: tuple[float, ...]
    quality_score: float
    evidence_ids: tuple[int, ...]
    created_at: str


@dataclass(frozen=True)
class SignatureChange:
    current_id: str
    reference_id: str
    distance: float | None
    classification: str
    changed_features: tuple[str, ...]
    disappeared_patterns: tuple[str, ...]
    new_patterns: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    conclusion: str = "ALTERAÇÃO ESTATÍSTICA; NÃO É FALHA CONFIRMADA"


@dataclass(frozen=True)
class HealthReport:
    id: str
    machine_id: str
    controller_id: str
    period_kind: PeriodKind
    period_start: str
    period_end: str
    session_ids: tuple[str, ...]
    indicators: tuple[HealthIndicator, ...]
    trends: tuple[TrendMetric, ...]
    signatures: tuple[OperationalSignature, ...]
    relevant_events: tuple[int, ...]
    anomaly_ids: tuple[str, ...]
    created_at: str
    diagnosis: str = "NÃO DETERMINADO"
    failure_probability: str = "NÃO CALCULADA"


class HealthRepository:
    def __init__(self,path:str|Path)->None:
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._schema()
    def _connect(self):
        connection=sqlite3.connect(self.path);connection.row_factory=sqlite3.Row;return connection
    def _schema(self):
        with self._connect() as connection:connection.executescript("""
          CREATE TABLE IF NOT EXISTS health_reports(id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS health_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,report_id TEXT NOT NULL,timestamp TEXT NOT NULL,action TEXT NOT NULL,payload_json TEXT NOT NULL);
        """)
    def save(self,report:HealthReport):
        payload=json.dumps(asdict(report),ensure_ascii=False,default=lambda v:v.value if isinstance(v,StrEnum) else str(v))
        with self._connect() as connection:
            connection.execute("INSERT INTO health_reports VALUES(?,?,?)",(report.id,payload,report.created_at));connection.execute("INSERT INTO health_audit(report_id,timestamp,action,payload_json) VALUES(?,?,?,?)",(report.id,report.created_at,"RELATÓRIO GERADO",payload))
    def list(self)->list[dict[str,Any]]:
        with self._connect() as connection:return [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM health_reports ORDER BY created_at DESC").fetchall()]
    def audit(self,report_id):
        with self._connect() as connection:return [dict(row) for row in connection.execute("SELECT * FROM health_audit WHERE report_id=?",(report_id,)).fetchall()]


class OperationalHealthEngine:
    MIN_SESSIONS=2
    def __init__(self,blackbox:BlackBoxStore,anomalies:AnomalyRepository,defrost:DefrostCycleAnalyzer,repository:HealthRepository)->None:
        self.blackbox,self.anomalies,self.defrost,self.repository=blackbox,anomalies,defrost,repository

    def analyze(self,machine_id:str,controller_id:str,session_ids:Iterable[str],period_kind:PeriodKind=PeriodKind.CUSTOM,custom_start:str|None=None,custom_end:str|None=None)->HealthReport:
        sessions=[self.blackbox.get_session(sid) for sid in dict.fromkeys(session_ids)]
        if not sessions:raise ValueError("DADOS INSUFICIENTES: nenhuma sessão.")
        start,end=self._period(sessions,period_kind,custom_start,custom_end);sessions=[s for s in sessions if start<=s.started_at<=end]
        ids=tuple(s.id for s in sessions);signatures=tuple(self.signature(s.id) for s in sessions)
        session_order={session_id:index for index,session_id in enumerate(ids)}
        anomaly_results=sorted((r for r in self.anomalies.list() if r.session_id in ids and r.state is AnalysisState.COMPLETED),key=lambda r:session_order[r.session_id])
        indicators=[]
        indicators.append(self._data_health(ids))
        indicators.append(self._event_health(ids,HealthDimension.CONTROL,(TimelineKind.ALARM,TimelineKind.STATE_CHANGE)))
        indicators.append(self._thermal_health(signatures))
        indicators.append(self._defrost_health(ids))
        indicators.append(self._event_health(ids,HealthDimension.COMMUNICATION,(TimelineKind.COMMUNICATION_LOSS,)))
        indicators.append(self._channel_health(ids,HealthDimension.COMPRESSOR,("compressor",)))
        indicators.append(self._channel_health(ids,HealthDimension.ELECTRICAL,("current_","voltage_","power_","pf","frequency","energy","thd")))
        trends=self._trends(ids,anomaly_results)
        general=self._general(indicators,trends,len(ids));indicators.append(general)
        relevant=tuple(dict.fromkeys(i for indicator in indicators for i in indicator.evidence_ids))
        report=HealthReport(f"HLT-{uuid.uuid4().hex[:12].upper()}",machine_id,controller_id,period_kind,start,end,ids,tuple(indicators),tuple(trends),signatures,relevant,tuple(r.id for r in anomaly_results),datetime.now().astimezone().isoformat())
        self.repository.save(report);return report

    def signature(self,session_id:str)->OperationalSignature:
        rows=self.blackbox.query(session_id);samples=[r for r in rows if r["kind"]==TimelineKind.SAMPLE.value]
        valid=[r for r in samples if isinstance(r["value"],(int,float)) and r["quality"]=="VÁLIDA"]
        groups={}
        for row in valid:groups.setdefault(row["variable_id"],[]).append(float(row["value"]))
        names=[];features=[]
        for variable,values in sorted(groups.items()):names.append(f"mean:{variable}");features.append(fmean(values))
        for kind in (TimelineKind.ALARM,TimelineKind.DEVIATION,TimelineKind.COMMUNICATION_LOSS,TimelineKind.RECOVERY):names.append(f"count:{kind.value}");features.append(float(sum(r["kind"]==kind.value for r in rows)))
        quality=len(valid)/len(samples) if samples else 0.0
        return OperationalSignature(f"SIG-{uuid.uuid4().hex[:10].upper()}",session_id,tuple(sorted(groups)),tuple(names),tuple(features),quality,tuple(r["id"] for r in rows),datetime.now().astimezone().isoformat())

    def compare_signatures(self,current:OperationalSignature,reference:OperationalSignature,threshold:float=.2)->SignatureChange:
        common=tuple(name for name in current.feature_names if name in reference.feature_names);cur=dict(zip(current.feature_names,current.features));ref=dict(zip(reference.feature_names,reference.features))
        if not common:return SignatureChange(current.id,reference.id,None,"DADOS INSUFICIENTES",(),tuple(reference.feature_names),tuple(current.feature_names),tuple(dict.fromkeys(current.evidence_ids+reference.evidence_ids)))
        scale=max(1.0,sum(abs(ref[n]) for n in common)/len(common));distance=(sum((cur[n]-ref[n])**2 for n in common)/len(common))**.5/scale
        changed=tuple(n for n in common if abs(cur[n]-ref[n])/max(1.0,abs(ref[n]))>threshold)
        return SignatureChange(current.id,reference.id,distance,"ASSINATURA ALTERADA" if changed else "ASSINATURA RECORRENTE",changed,tuple(n for n in reference.feature_names if n not in cur),tuple(n for n in current.feature_names if n not in ref),tuple(dict.fromkeys(current.evidence_ids+reference.evidence_ids)))

    def _data_health(self,ids):
        rows=[r for sid in ids for r in self.blackbox.query(sid,kinds=(TimelineKind.SAMPLE,))];valid=[r for r in rows if r["quality"]=="VÁLIDA" and r["value"] is not None];quality=len(valid)/len(rows) if rows else 0
        if not rows:return self._empty(HealthDimension.DATA)
        return HealthIndicator(HealthDimension.DATA,100*quality,self._classify(100*quality),quality,(f"{len(valid)}/{len(rows)} amostras válidas",),tuple(r["id"] for r in rows),"Indicador de completude/qualidade; não é probabilidade.")
    def _event_health(self,ids,dimension,kinds):
        rows=[r for sid in ids for r in self.blackbox.query(sid,kinds=kinds)];bad=[r for r in rows if r["kind"] in (TimelineKind.ALARM.value,TimelineKind.COMMUNICATION_LOSS.value)]
        score=max(0,100-10*len(bad))
        return HealthIndicator(dimension,score,self._classify(score),1.0,(f"{len(bad)} eventos adversos",),tuple(r["id"] for r in rows),"Penalização operacional por eventos registrados; não estima falha.")
    def _thermal_health(self,signatures):
        available=[s for s in signatures if any("temp" in n.lower() or "press" in n.lower() for n in s.feature_names)]
        if not available:return self._empty(HealthDimension.THERMAL)
        quality=fmean(s.quality_score for s in available);score=100*quality
        return HealthIndicator(HealthDimension.THERMAL,score,self._classify(score),quality,("Assinaturas térmicas disponíveis",),tuple(i for s in available for i in s.evidence_ids),"Baseado na qualidade e disponibilidade das assinaturas térmicas.")
    def _defrost_health(self,ids):
        cycles=[cycle for sid in ids for cycle in self.defrost.identify(sid)]
        if not cycles:return self._empty(HealthDimension.DEFROST)
        complete=sum(c.status is CycleStatus.COMPLETE for c in cycles);score=100*complete/len(cycles);quality=fmean(c.quality_score for c in cycles)
        return HealthIndicator(HealthDimension.DEFROST,score,self._classify(score),quality,(f"{complete}/{len(cycles)} ciclos completos",),tuple(i for c in cycles for i in c.evidence_ids),"Completude e qualidade dos ciclos observados.")
    def _channel_health(self,ids,dimension,prefixes):
        rows=[r for sid in ids for r in self.blackbox.query(sid,kinds=(TimelineKind.SAMPLE,)) if any((r["variable_id"] or "").lower().startswith(p) or p in (r["variable_id"] or "").lower() for p in prefixes)]
        if not rows:return self._empty(dimension,HealthClassification.NOT_CONNECTED)
        valid=[r for r in rows if r["quality"]=="VÁLIDA" and r["value"] is not None];quality=len(valid)/len(rows);score=100*quality
        return HealthIndicator(dimension,score,self._classify(score),quality,(f"{len(valid)}/{len(rows)} dados válidos",),tuple(r["id"] for r in rows),"Disponibilidade e qualidade da dimensão; não diagnostica componente.")
    def _trends(self,ids,anomalies):
        scores=[r.anomaly_score for r in anomalies if r.anomaly_score is not None];alarm_counts=[sum(r["kind"]==TimelineKind.ALARM.value for r in self.blackbox.query(sid)) for sid in ids]
        recovery=[fmean([(r["timestamp_ns"]-prev["timestamp_ns"])/1e9 for prev,r in zip(rows,rows[1:]) if r["kind"]==TimelineKind.RECOVERY.value]) if any(r["kind"]==TimelineKind.RECOVERY.value for r in rows) else 0 for sid in ids for rows in [self.blackbox.query(sid)]]
        return tuple(self._trend(name,values) for name,values in (("ANOMALIAS",scores),("ALARMES",alarm_counts),("RECUPERAÇÃO",recovery)))
    @staticmethod
    def _trend(name,values):
        values=tuple(float(v) for v in values);slope=(values[-1]-values[0])/(len(values)-1) if len(values)>=2 else None;direction="AUMENTANDO" if slope and slope>0 else "REDUZINDO" if slope and slope<0 else "ESTÁVEL" if slope==0 else "NÃO DETERMINADO"
        return TrendMetric(name,values,slope,direction,len(values)>=3 and slope is not None and abs(slope)>0,())
    def _general(self,indicators,trends,count):
        usable=[i for i in indicators if i.score is not None]
        if count<self.MIN_SESSIONS or len(usable)<3:return self._empty(HealthDimension.GENERAL)
        score=fmean(i.score for i in usable);degradation=any(t.persistent and t.direction=="AUMENTANDO" for t in trends)
        classification=HealthClassification.DEGRADATION_INDICATED if degradation else self._classify(score)
        return HealthIndicator(HealthDimension.GENERAL,score,classification,fmean(i.quality_score for i in usable),(f"{len(usable)} dimensões com dados",)+(("Tendência persistente crescente",) if degradation else ()),tuple(i for item in usable for i in item.evidence_ids),"Agregação operacional das dimensões disponíveis; não é probabilidade de falha.")
    @staticmethod
    def _classify(score):
        return HealthClassification.NORMAL if score>=90 else HealthClassification.ATTENTION if score>=75 else HealthClassification.BEHAVIOR_CHANGE if score>=50 else HealthClassification.DEGRADATION_INDICATED
    @staticmethod
    def _empty(dimension,classification=HealthClassification.INSUFFICIENT):return HealthIndicator(dimension,None,classification,0.0,("SEM DADOS",),(),"DADOS INSUFICIENTES / NÃO DETERMINADO")
    @staticmethod
    def _period(sessions,kind,start,end):
        latest=max(s.started_at for s in sessions)
        if kind is PeriodKind.CUSTOM:
            if not start or not end:raise ValueError("Período personalizado exige início e fim.")
            return start,end
        if kind is PeriodKind.SESSION:return min(s.started_at for s in sessions),latest
        days={PeriodKind.DAY:1,PeriodKind.WEEK:7,PeriodKind.MONTH:30}[kind]
        begin=(datetime.fromisoformat(latest)-timedelta(days=days)).isoformat();return begin,latest
