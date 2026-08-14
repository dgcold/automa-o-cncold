from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .field_diagnostics import BlackBoxStore
from .analysis_integration import SessionEvidenceInterpreter


class ConclusionState(StrEnum):
    OBSERVED = "OBSERVADO"
    INDICATION = "INDICAÇÃO"
    HYPOTHESIS = "HIPÓTESE"
    DISCARDED = "HIPÓTESE DESCARTADA"
    SUFFICIENT_EVIDENCE = "EVIDÊNCIA SUFICIENTE"
    CONFIRMED = "CONFIRMADO"


@dataclass(frozen=True)
class TechnicalRule:
    id: str
    version: str
    description: str
    context: str
    hypothesis: str
    favorable_facts: tuple[str, ...]
    contrary_facts: tuple[str, ...] = ()
    required_confirmation_facts: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    recommended_test: str = "NÃO DETERMINADO"
    source: str = "REGRA TÉCNICA VALIDADA"
    enabled: bool = True


def deterministic_observation_rules() -> tuple[TechnicalRule, ...]:
    """Cautious rules whose favorable facts are measurable relations, not scenario labels."""
    return (
        TechnicalRule("R-ELETRICA-FASES-001","1.0","Diferença relativa observada entre correntes L1/L2/L3","SIMULADOR_ELETRICO",
            "Possível desequilíbrio de corrente entre fases.",( "phase_current_imbalance",),required_confirmation_facts=("medicao_fisica_tensao_corrente",),
            missing_information=("Tensão entre fases e inspeção das conexões não estão disponíveis na telemetria.",),
            recommended_test="Verificar alimentação, conexões, tensão e corrente entre fases.",source="CRITÉRIO DETERMINÍSTICO SOBRE AMOSTRAS L1/L2/L3"),
        TechnicalRule("R-COMPRESSOR-RETORNO-001","1.0","Comando verdadeiro sem retorno de estado do compressor","SIMULADOR_ELETRICO",
            "Possível comando do compressor sem confirmação de funcionamento.",( "compressor_command_without_feedback",),required_confirmation_facts=("verificacao_fisica_circuito_potencia",),
            missing_information=("O motivo físico da ausência de retorno não está disponível na telemetria.",),
            recommended_test="Verificar proteções, alimentação, circuito de potência e intertravamentos.",source="CRITÉRIO DETERMINÍSTICO SOBRE COMANDO E RETORNO"),
        TechnicalRule("R-VENTILADOR-COND-001","1.0","Retorno desligado em estado de refrigeração","SIMULADOR_ELETRICO","Possível falha de confirmação do ventilador do condensador.",( "condenser_fan_without_feedback",),required_confirmation_facts=("verificacao_fisica_ventilador",),recommended_test="Verificar comando, retorno, alimentação e funcionamento do ventilador."),
        TechnicalRule("R-SENSOR-001","1.0","Leitura ausente ou qualidade inválida","SIMULADOR_ELETRICO","Possível sensor inválido ou leitura inconsistente.",( "invalid_sensor_reading",),required_confirmation_facts=("verificacao_fisica_sensor",),recommended_test="Verificar sensor, cabeamento, conexão e leitura local."),
        TechnicalRule("R-COMUNICACAO-001","1.0","Perda de comunicação observada","SIMULADOR_ELETRICO","Possível interrupção de comunicação.",( "communication_loss_observed",),required_confirmation_facts=("verificacao_fisica_rede",),recommended_test="Verificar meio físico, alimentação, endereçamento e estabilidade da comunicação."),
        TechnicalRule("R-DEGELO-001","1.0","Ciclo ou resposta térmica de degelo incompleta","SIMULADOR_ELETRICO","Possível ciclo de degelo incompleto.",( "incomplete_defrost_cycle",),required_confirmation_facts=("verificacao_fisica_degelo",),recommended_test="Verificar fases, aquecimento, gotejamento e retorno à refrigeração."),
        TechnicalRule("R-RECUPERACAO-001","1.0","Resposta térmica lenta após retorno","SIMULADOR_ELETRICO","Possível recuperação térmica lenta.",( "slow_thermal_recovery",),required_confirmation_facts=("verificacao_fisica_carga_termica",),recommended_test="Verificar carga térmica, circulação de ar e capacidade frigorífica."),
        TechnicalRule("R-CORRENTE-COMP-001","1.0","Corrente do compressor elevada e sustentada","SIMULADOR_ELETRICO","Possível corrente elevada do compressor.",( "high_compressor_current",),required_confirmation_facts=("medicao_fisica_corrente",),recommended_test="Verificar corrente, tensão, pressões e condição mecânica do compressor."),
    )


@dataclass(frozen=True)
class EvidenceArgument:
    fact: str
    text: str
    evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class HypothesisConclusion:
    id: str
    rule_id: str
    rule_version: str
    description: str
    confidence: float
    favorable: tuple[EvidenceArgument, ...]
    contrary: tuple[EvidenceArgument, ...]
    evidence_ids: tuple[int, ...]
    first_deviation_id: int | None
    context: str
    missing_confirmation: tuple[str, ...]
    recommended_test: str
    state: ConclusionState
    created_at: str
    event_id: int | None = None
    session_id: str = ""
    notes: str = ""
    causality: str = "NÃO ESTABELECIDA"


class RuleCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> tuple[TechnicalRule, ...]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rules = []
        for item in payload.get("rules", []):
            for key in ("favorable_facts","contrary_facts","required_confirmation_facts","missing_information"):
                item[key] = tuple(item.get(key, ()))
            rules.append(TechnicalRule(**item))
        return tuple(rules)


class DiagnosticRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._schema()

    def _connect(self):
        connection=sqlite3.connect(self.path);connection.row_factory=sqlite3.Row;return connection

    def _schema(self):
        with self._connect() as connection:
            connection.executescript("""
              CREATE TABLE IF NOT EXISTS conclusions(
                id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS conclusion_audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT, conclusion_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                notes TEXT NOT NULL, payload_json TEXT NOT NULL);
            """)

    def save(self, conclusion: HypothesisConclusion, action: str="CRIADA", actor: str="MOTOR DE REGRAS") -> None:
        payload=json.dumps(asdict(conclusion),ensure_ascii=False,default=lambda value:value.value if isinstance(value,StrEnum) else str(value))
        now=datetime.now().astimezone().isoformat()
        with self._connect() as connection:
            connection.execute("INSERT INTO conclusions VALUES(?,?,?,?,?)",(conclusion.id,payload,conclusion.state.value,conclusion.created_at,now))
            connection.execute("INSERT INTO conclusion_audit(conclusion_id,timestamp,action,actor,notes,payload_json) VALUES(?,?,?,?,?,?)",(conclusion.id,now,action,actor,conclusion.notes,payload))

    def get(self, conclusion_id: str) -> HypothesisConclusion:
        with self._connect() as connection:row=connection.execute("SELECT payload_json FROM conclusions WHERE id=?",(conclusion_id,)).fetchone()
        if row is None:raise KeyError(conclusion_id)
        return self._decode(json.loads(row[0]))

    def list(self) -> list[HypothesisConclusion]:
        with self._connect() as connection:rows=connection.execute("SELECT payload_json FROM conclusions ORDER BY created_at DESC").fetchall()
        return [self._decode(json.loads(row[0])) for row in rows]

    def transition(self, conclusion_id: str, target: ConclusionState, actor: str, notes: str="", confirmation_evidence: Iterable[int]=()) -> HypothesisConclusion:
        current=self.get(conclusion_id)
        allowed={
            ConclusionState.HYPOTHESIS:{ConclusionState.DISCARDED,ConclusionState.SUFFICIENT_EVIDENCE},
            ConclusionState.SUFFICIENT_EVIDENCE:{ConclusionState.DISCARDED,ConclusionState.CONFIRMED},
            ConclusionState.OBSERVED:{ConclusionState.INDICATION},ConclusionState.INDICATION:{ConclusionState.HYPOTHESIS},
            ConclusionState.DISCARDED:set(),ConclusionState.CONFIRMED:set(),
        }
        if target not in allowed[current.state]:raise ValueError(f"Transição inválida: {current.state.value} -> {target.value}")
        confirmation_evidence=tuple(int(value) for value in confirmation_evidence)
        if target is ConclusionState.SUFFICIENT_EVIDENCE and current.missing_confirmation:
            raise ValueError("Ainda existem requisitos de confirmação pendentes.")
        if target is ConclusionState.CONFIRMED and not confirmation_evidence:
            raise ValueError("CONFIRMADO exige evidência de confirmação explícita.")
        updated=HypothesisConclusion(**{**asdict(current),"favorable":current.favorable,"contrary":current.contrary,
            "evidence_ids":tuple(dict.fromkeys(current.evidence_ids+confirmation_evidence)),"missing_confirmation":current.missing_confirmation,
            "state":target,"notes":notes,"causality":"CONFIRMADA MANUALMENTE" if target is ConclusionState.CONFIRMED else current.causality})
        payload=json.dumps(asdict(updated),ensure_ascii=False,default=lambda value:value.value if isinstance(value,StrEnum) else str(value));now=datetime.now().astimezone().isoformat()
        with self._connect() as connection:
            connection.execute("UPDATE conclusions SET payload_json=?,state=?,updated_at=? WHERE id=?",(payload,target.value,now,conclusion_id))
            connection.execute("INSERT INTO conclusion_audit(conclusion_id,timestamp,action,actor,notes,payload_json) VALUES(?,?,?,?,?,?)",(conclusion_id,now,target.value,actor,notes,payload))
        return updated

    def audit(self, conclusion_id: str) -> list[dict[str,Any]]:
        with self._connect() as connection:return [dict(row) for row in connection.execute("SELECT * FROM conclusion_audit WHERE conclusion_id=? ORDER BY id",(conclusion_id,)).fetchall()]

    @staticmethod
    def _decode(data):
        data["state"]=ConclusionState(data["state"])
        data["favorable"]=tuple(EvidenceArgument(**{**item,"evidence_ids":tuple(item["evidence_ids"])}) for item in data["favorable"])
        data["contrary"]=tuple(EvidenceArgument(**{**item,"evidence_ids":tuple(item["evidence_ids"])}) for item in data["contrary"])
        data["evidence_ids"]=tuple(data["evidence_ids"]);data["missing_confirmation"]=tuple(data["missing_confirmation"])
        return HypothesisConclusion(**data)


class ExplainableDiagnosticEngine:
    def __init__(self, evidence_store: BlackBoxStore, repository: DiagnosticRepository, rules: Iterable[TechnicalRule]) -> None:
        self.evidence_store,self.repository,self.rules=evidence_store,repository,tuple(rules)

    def evaluate(self, session_id: str, facts: Mapping[str,Iterable[int]], *, context: str,
                 event_id: int|None=None, first_deviation_id: int|None=None,
                 fact_descriptions: Mapping[str,str]|None=None) -> list[HypothesisConclusion]:
        session_id=self.evidence_store.resolve_session_id(session_id)
        valid_ids={row["id"] for row in self.evidence_store.query(session_id)}
        normalized={fact:tuple(int(i) for i in ids) for fact,ids in facts.items()}
        for ids in normalized.values():
            if not set(ids)<=valid_ids:raise ValueError("Evidência vinculada não pertence à sessão.")
        output=[]
        for rule in self.rules:
            if not rule.enabled or rule.context not in (context,"QUALQUER"):continue
            favorable=[EvidenceArgument(fact,(fact_descriptions or {}).get(fact,f"Fato observado: {fact}"),normalized[fact]) for fact in rule.favorable_facts if normalized.get(fact)]
            contrary=[EvidenceArgument(fact,f"Evidência contrária: {fact}",normalized[fact]) for fact in rule.contrary_facts if normalized.get(fact)]
            if not favorable:continue
            support=len(favorable)/max(1,len(rule.favorable_facts));opposition=len(contrary)/max(1,len(rule.contrary_facts)) if rule.contrary_facts else 0
            confidence=max(0.0,min(0.95,0.70*support-0.35*opposition))
            missing=tuple(fact for fact in rule.required_confirmation_facts if not normalized.get(fact))+rule.missing_information
            evidence=tuple(dict.fromkeys(i for argument in favorable+contrary for i in argument.evidence_ids))
            conclusion=HypothesisConclusion(f"H-{uuid.uuid4().hex[:10].upper()}",rule.id,rule.version,rule.hypothesis,confidence,
                tuple(favorable),tuple(contrary),evidence,first_deviation_id,context,missing,rule.recommended_test,
                ConclusionState.HYPOTHESIS,datetime.now().astimezone().isoformat(),event_id,session_id)
            self.repository.save(conclusion);output.append(conclusion)
        return sorted(output,key=lambda item:item.confidence,reverse=True)

    def evaluate_recorded(self, identifier: str, *, context: str="SIMULADOR_ELETRICO") -> list[HypothesisConclusion]:
        """Evaluate facts derived from the session samples and their real record IDs."""
        interpreter=SessionEvidenceInterpreter(self.evidence_store);session_id=interpreter.resolve(identifier)
        extracted=interpreter.extract(session_id);facts={item.name:item.evidence_ids for item in extracted};descriptions={item.name:interpreter.evidence_text(item) for item in extracted}
        rows=self.evidence_store.query(session_id)
        event=next((row for row in rows if row["kind"] in ("ALARME","DESVIO")),None)
        deviation=next((row for row in rows if row["kind"]=="DESVIO"),None)
        return self.evaluate(session_id,facts,context=context,event_id=event["id"] if event else None,
            first_deviation_id=deviation["id"] if deviation else None,fact_descriptions=descriptions)

    def competing(self, conclusions: Iterable[HypothesisConclusion]) -> list[dict[str,Any]]:
        return [{"id":item.id,"description":item.description,"confidence":item.confidence,"state":item.state.value,
                 "favorable":len(item.favorable),"contrary":len(item.contrary),"causality":item.causality} for item in sorted(conclusions,key=lambda x:x.confidence,reverse=True)]
