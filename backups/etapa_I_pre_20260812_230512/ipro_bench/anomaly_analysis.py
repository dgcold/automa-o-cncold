from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from .baseline import BaselineRepository, BaselineStatus
from .field_diagnostics import BlackBoxStore, TimelineKind


class AnalysisState(StrEnum):
    COMPLETED = "CONCLUÍDA"
    ABSTAINED = "ABSTENÇÃO"


class AnomalyClass(StrEnum):
    NORMAL = "COMPORTAMENTO NORMAL"
    ANOMALOUS = "ANOMALIA DETECTADA"
    UNDETERMINED = "NÃO DETERMINADO"


@dataclass(frozen=True)
class AlgorithmVersion:
    name: str = "CNCold Baseline Distance"
    version: str = "1.0.0"
    method: str = "distância padronizada explicável"
    anomaly_threshold: float = 3.0
    minimum_samples: int = 3
    minimum_quality: float = 0.8


@dataclass(frozen=True)
class ContributingFactor:
    variable_id: str
    observed_average: float
    baseline_average: float
    standardized_distance: float | None
    contribution: float
    direction: str
    first_anomalous_timestamp: str | None
    evidence_ids: tuple[int, ...]
    explanation: str


@dataclass(frozen=True)
class AnomalyResult:
    id: str
    session_id: str
    baseline_id: str
    algorithm_name: str
    algorithm_version: str
    state: AnalysisState
    classification: AnomalyClass
    anomaly_score: float | None
    confidence: float
    quality_score: float
    coverage: float
    period_start: str | None
    period_end: str | None
    variables: tuple[str, ...]
    factors: tuple[ContributingFactor, ...]
    evidence_ids: tuple[int, ...]
    explanation: str
    abstention_reason: str | None
    created_at: str
    causality: str = "NÃO ESTABELECIDA"
    root_cause: str = "NÃO DETERMINADA"
    confirmed_diagnosis: str = "NÃO DETERMINADO"


@dataclass(frozen=True)
class BehaviorCluster:
    id: str
    session_ids: tuple[str, ...]
    centroid: tuple[float, ...]
    variables: tuple[str, ...]
    recurring: bool
    interpretation: str = "AGRUPAMENTO DE SEMELHANÇA; NÃO É DIAGNÓSTICO"


class AnomalyRepository:
    def __init__(self,path:str|Path)->None:
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._schema()

    def _connect(self):
        connection=sqlite3.connect(self.path);connection.row_factory=sqlite3.Row;return connection

    def _schema(self):
        with self._connect() as connection:
            connection.executescript("""
              CREATE TABLE IF NOT EXISTS anomaly_results(
                id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,session_id TEXT NOT NULL,
                baseline_id TEXT NOT NULL,algorithm_version TEXT NOT NULL,created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS anomaly_audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,result_id TEXT NOT NULL,timestamp TEXT NOT NULL,
                action TEXT NOT NULL,payload_json TEXT NOT NULL);
            """)

    def save(self,result:AnomalyResult)->None:
        payload=json.dumps(asdict(result),ensure_ascii=False,default=lambda v:v.value if isinstance(v,StrEnum) else str(v))
        with self._connect() as connection:
            connection.execute("INSERT INTO anomaly_results VALUES(?,?,?,?,?,?)",(result.id,payload,result.session_id,result.baseline_id,result.algorithm_version,result.created_at))
            connection.execute("INSERT INTO anomaly_audit(result_id,timestamp,action,payload_json) VALUES(?,?,?,?)",(result.id,result.created_at,"ANÁLISE REGISTRADA",payload))

    def list(self)->list[AnomalyResult]:
        with self._connect() as connection:rows=connection.execute("SELECT payload_json FROM anomaly_results ORDER BY created_at DESC").fetchall()
        return [self._decode(json.loads(row[0])) for row in rows]

    def audit(self,result_id:str)->list[dict[str,Any]]:
        with self._connect() as connection:return [dict(row) for row in connection.execute("SELECT * FROM anomaly_audit WHERE result_id=? ORDER BY id",(result_id,)).fetchall()]

    def compare_versions(self,session_id:str)->list[dict[str,Any]]:
        with self._connect() as connection:rows=connection.execute("SELECT payload_json FROM anomaly_results WHERE session_id=? ORDER BY created_at",(session_id,)).fetchall()
        return [{"id":item.id,"version":item.algorithm_version,"score":item.anomaly_score,"classification":item.classification.value,"confidence":item.confidence} for item in (self._decode(json.loads(row[0])) for row in rows)]

    @staticmethod
    def _decode(data):
        data["state"]=AnalysisState(data["state"]);data["classification"]=AnomalyClass(data["classification"])
        data["variables"]=tuple(data["variables"]);data["evidence_ids"]=tuple(data["evidence_ids"])
        data["factors"]=tuple(ContributingFactor(**{**item,"evidence_ids":tuple(item["evidence_ids"])}) for item in data["factors"])
        return AnomalyResult(**data)


class AnomalyEngine:
    def __init__(self,blackbox:BlackBoxStore,baselines:BaselineRepository,repository:AnomalyRepository,algorithm:AlgorithmVersion=AlgorithmVersion())->None:
        self.blackbox,self.baselines,self.repository,self.algorithm=blackbox,baselines,repository,algorithm

    def analyze(self,session_id:str,baseline_id:str)->AnomalyResult:
        baseline=self.baselines.get(baseline_id)
        if baseline.status not in (BaselineStatus.VALIDATED,BaselineStatus.ACTIVE):raise ValueError("Baseline deve estar VALIDADO ou ATIVO.")
        rows=self.blackbox.query(session_id,kinds=(TimelineKind.SAMPLE,))
        valid=[r for r in rows if isinstance(r["value"],(int,float)) and r["quality"]=="VÁLIDA"]
        quality=len(valid)/len(rows) if rows else 0.0
        if len(rows)<self.algorithm.minimum_samples:return self._abstain(session_id,baseline_id,quality,"DADOS INSUFICIENTES")
        if quality<self.algorithm.minimum_quality:return self._abstain(session_id,baseline_id,quality,"QUALIDADE INADEQUADA")
        profiles={p.variable_id:p for p in baseline.profiles};groups={}
        for row in valid:
            if row["variable_id"] in profiles:groups.setdefault(row["variable_id"],[]).append(row)
        coverage=len(groups)/len(profiles) if profiles else 0.0
        if not profiles or coverage<0.5:return self._abstain(session_id,baseline_id,quality,"COBERTURA DE VARIÁVEIS INSUFICIENTE",coverage)
        factors=[]
        for variable,items in sorted(groups.items()):
            profile=profiles[variable];observed=fmean(float(r["value"]) for r in items);delta=observed-profile.average
            if profile.dispersion>0:distance=abs(delta)/profile.dispersion
            elif delta==0:distance=0.0
            else:distance=None
            contribution=min(1.0,(distance or 0)/self.algorithm.anomaly_threshold) if distance is not None else 0.0
            first=next((r for r in items if float(r["value"])<profile.normal_low or float(r["value"])>profile.normal_high),None)
            factors.append(ContributingFactor(variable,observed,profile.average,distance,contribution,"ACIMA" if delta>0 else "ABAIXO" if delta<0 else "IGUAL",
                first["timestamp"] if first else None,tuple(r["id"] for r in items),
                f"Média observada {observed:.4g}; referência {profile.average:.4g}; distância {'NÃO DETERMINADA' if distance is None else f'{distance:.2f} dispersões'}."))
        usable=[f for f in factors if f.standardized_distance is not None]
        if not usable:return self._abstain(session_id,baseline_id,quality,"VARIABILIDADE DE REFERÊNCIA INSUFICIENTE",coverage)
        score=100*fmean(f.contribution for f in usable);classification=AnomalyClass.ANOMALOUS if any((f.standardized_distance or 0)>=self.algorithm.anomaly_threshold for f in usable) else AnomalyClass.NORMAL
        confidence=min(.95,quality*coverage*(len(usable)/len(factors)))
        evidence=tuple(dict.fromkeys(i for factor in factors for i in factor.evidence_ids));period=[r["timestamp"] for r in rows]
        explanation=("Comportamento fora da faixa padronizada do baseline." if classification is AnomalyClass.ANOMALOUS else "Comportamento dentro do padrão estatístico avaliado.")+" Não estabelece causa-raiz."
        result=AnomalyResult(f"AI-{uuid.uuid4().hex[:12].upper()}",session_id,baseline_id,self.algorithm.name,self.algorithm.version,AnalysisState.COMPLETED,classification,score,confidence,quality,coverage,min(period),max(period),tuple(groups),tuple(sorted(factors,key=lambda f:f.contribution,reverse=True)),evidence,explanation,None,datetime.now().astimezone().isoformat())
        self.repository.save(result);return result

    def _abstain(self,session_id,baseline_id,quality,reason,coverage=0.0):
        result=AnomalyResult(f"AI-{uuid.uuid4().hex[:12].upper()}",session_id,baseline_id,self.algorithm.name,self.algorithm.version,AnalysisState.ABSTAINED,AnomalyClass.UNDETERMINED,None,0.0,quality,coverage,None,None,(),(),(),"DADOS INSUFICIENTES / NÃO DETERMINADO",reason,datetime.now().astimezone().isoformat())
        self.repository.save(result);return result

    def cluster_sessions(self,session_ids:Iterable[str],variables:Iterable[str],distance_threshold:float=0.25)->list[BehaviorCluster]:
        variables=tuple(variables);vectors=[]
        for session_id in session_ids:
            vector=[]
            for variable in variables:
                rows=[r for r in self.blackbox.query(session_id,variable_id=variable,kinds=(TimelineKind.SAMPLE,)) if isinstance(r["value"],(int,float)) and r["quality"]=="VÁLIDA"]
                if not rows:break
                vector.append(fmean(float(r["value"]) for r in rows))
            if len(vector)==len(variables):vectors.append((session_id,tuple(vector)))
        clusters=[]
        for session_id,vector in vectors:
            match=None
            for group in clusters:
                scale=max(1.0,math.sqrt(sum(v*v for v in group["centroid"])))
                distance=math.sqrt(sum((a-b)**2 for a,b in zip(vector,group["centroid"])))/scale
                if distance<=distance_threshold:match=group;break
            if match:match["items"].append((session_id,vector));match["centroid"]=tuple(fmean(v[i] for _,v in match["items"]) for i in range(len(variables)))
            else:clusters.append({"items":[(session_id,vector)],"centroid":vector})
        return [BehaviorCluster(f"CLU-{index:03d}",tuple(s for s,_ in group["items"]),group["centroid"],variables,len(group["items"])>=2) for index,group in enumerate(clusters,1)]
