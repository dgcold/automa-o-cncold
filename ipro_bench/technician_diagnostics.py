from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


VARIABLE_LABELS = {
    "current_total": "CORRENTE TOTAL", "current_compressor": "CORRENTE DO COMPRESSOR",
    "current_l1": "CORRENTE FASE L1", "current_l2": "CORRENTE FASE L2", "current_l3": "CORRENTE FASE L3",
    "temperature_chamber": "TEMPERATURA DA CÂMARA", "temperature_evaporator": "TEMPERATURA DO EVAPORADOR",
    "pressure_suction": "PRESSÃO DE SUCÇÃO", "pressure_discharge": "PRESSÃO DE DESCARGA",
    "compressor_command": "COMANDO DO COMPRESSOR", "compressor": "COMPRESSOR",
    "evaporator_fan": "VENTILADOR DO EVAPORADOR", "condenser_fan": "VENTILADOR DO CONDENSADOR",
    "defrost": "DEGELO", "dripping": "GOTEJAMENTO", "communication": "COMUNICAÇÃO",
}


def technician_label(variable_id: str | None) -> str:
    return "NÃO DETERMINADO" if not variable_id else VARIABLE_LABELS.get(variable_id, variable_id.replace("_", " ").upper())


def display_value(value: Any, unit: str = "") -> str:
    if value is None: return "SEM DADOS"
    if isinstance(value, bool): return "LIGADO" if value else "DESLIGADO"
    if isinstance(value,float): value=f"{value:.2f}".replace(".",",")
    return f"{value} {unit}".strip()


@dataclass(frozen=True)
class FirstDeviation:
    timestamp: str; variable_id: str; variable: str; previous_value: Any; current_value: Any
    difference: float | None; expected: str; observed: str; severity: str; evidence_ids: tuple[int, ...]


@dataclass(frozen=True)
class DiagnosticPresentation:
    equipment: str; session_id: str; date: str; duration: str; machine_status: str; anomaly: str
    first_deviation: FirstDeviation | None; what_happened: str; observations: tuple[str, ...]
    evidence_ids: tuple[int, ...]; hypotheses: tuple[str, ...]; impact: str
    recommended_checks: tuple[str, ...]; confidence: float | None
    technician_confirmation: str = "PENDENTE"; raw_records: tuple[dict[str, Any], ...] = ()


class ConfirmationDecision(StrEnum):
    CONFIRMED = "CONFIRMADO PELO TÉCNICO"
    REJECTED = "HIPÓTESE REJEITADA"
    INCONCLUSIVE = "INCONCLUSIVO"


class TechnicianConfirmationRepository:
    def __init__(self, path: str | Path) -> None:
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS technician_confirmations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,technician TEXT NOT NULL,
            timestamp TEXT NOT NULL,diagnosis TEXT NOT NULL,decision TEXT NOT NULL,observation TEXT NOT NULL)""")

    def record(self,session_id:str,technician:str,diagnosis:str,decision:ConfirmationDecision,observation:str=""):
        if not technician.strip(): raise ValueError("O técnico deve ser identificado.")
        timestamp=datetime.now().astimezone().isoformat()
        with sqlite3.connect(self.path) as c:
            cursor=c.execute("INSERT INTO technician_confirmations(session_id,technician,timestamp,diagnosis,decision,observation) VALUES(?,?,?,?,?,?)",
                (session_id,technician.strip(),timestamp,diagnosis,decision.value,observation.strip()))
        return {"id":cursor.lastrowid,"session_id":session_id,"technician":technician.strip(),"timestamp":timestamp,
                "diagnosis":diagnosis,"decision":decision.value,"observation":observation.strip()}

    def latest(self,session_id:str):
        with sqlite3.connect(self.path) as c:
            c.row_factory=sqlite3.Row; row=c.execute("SELECT * FROM technician_confirmations WHERE session_id=? ORDER BY id DESC LIMIT 1",(session_id,)).fetchone()
        return dict(row) if row else None


class TechnicianDiagnosticEngine:
    """Interprets read-only black-box evidence without converting hypotheses into facts."""
    VALID_QUALITY={"VÁLIDA","VALID","GOOD"}

    def analyze(self,session_id:str,rows:Iterable[dict[str,Any]],*,equipment:str="iPro / Máquina"):
        records=tuple(dict(r) for r in rows); samples=[r for r in records if r.get("value") is not None and self._quality_ok(r)]
        first=self._first_deviation(records,samples); result=self._compressor(samples) or self._phases(samples)
        if result: anomaly,happened,observations,hypotheses,impact,checks,confidence,evidence=result
        elif first:
            anomaly="ANOMALIA DETECTADA"; happened=f"O primeiro desvio envolveu {first.variable}."; observations=(first.observed,)
            hypotheses=("O desvio requer verificação física e correlação com as demais evidências.",)
            impact="Impacto não determinado pelos dados disponíveis."; checks=("Verificar as condições associadas ao primeiro desvio.",)
            confidence=.50; evidence=first.evidence_ids
        else:
            anomaly="DADOS INSUFICIENTES"; happened="Não há evidência suficiente para determinar uma anomalia."
            observations=("SEM DADOS",); hypotheses=("NÃO DETERMINADO",); impact="NÃO DETERMINADO"
            checks=("Coletar dados válidos adicionais.",); confidence=None; evidence=()
        duration="NÃO DETERMINADO"
        if records and records[0].get("timestamp_ns") is not None and records[-1].get("timestamp_ns") is not None:
            duration=f"{max(0,records[-1]['timestamp_ns']-records[0]['timestamp_ns'])/1e9:.1f} s"
        timestamps=[r.get("timestamp") for r in records if r.get("timestamp")]
        evidence=tuple(dict.fromkeys((*evidence,*(first.evidence_ids if first else ()))))
        return DiagnosticPresentation(equipment,session_id,timestamps[0] if timestamps else "NÃO DETERMINADO",duration,
            anomaly,anomaly,first,happened,observations,evidence,hypotheses,impact,checks,confidence,raw_records=records)

    def analyze_families(self,session_id:str,rows:Iterable[dict[str,Any]],facts:Iterable[Any],*,equipment:str="iPro / Máquina"):
        base=self.analyze(session_id,rows,equipment=equipment);facts=tuple(facts)
        if not facts or base.anomaly in {"DESEQUILÍBRIO DE FASES","COMANDO SEM CONFIRMAÇÃO DO COMPRESSOR"}:return base
        labels={"condenser_fan_without_feedback":"POSSÍVEL FALHA DE CONFIRMAÇÃO DO VENTILADOR DO CONDENSADOR","invalid_sensor_reading":"POSSÍVEL SENSOR INVÁLIDO / LEITURA INCONSISTENTE","communication_loss_observed":"PERDA DE COMUNICAÇÃO OBSERVADA","incomplete_defrost_cycle":"POSSÍVEL DEGELO INCOMPLETO","slow_thermal_recovery":"POSSÍVEL RECUPERAÇÃO TÉRMICA LENTA","high_compressor_current":"POSSÍVEL CORRENTE ELEVADA DO COMPRESSOR"}
        primary=facts[0];anomaly=labels.get(primary.name,"ANOMALIA DETECTADA")
        evidence=tuple(dict.fromkeys(identifier for fact in facts for identifier in fact.evidence_ids))
        return DiagnosticPresentation(base.equipment,base.session_id,base.date,base.duration,"ANOMALIA DETECTADA",anomaly,base.first_deviation,
            primary.description,tuple(f.description for f in facts),evidence,(anomaly.capitalize()+"; requer confirmação técnica.",),
            "Impacto deve ser avaliado conforme a família de evidência e a condição física da máquina.",
            ("Verificar fisicamente os componentes e grandezas indicados pelas evidências.",),min(.90,.65+.03*len(facts)),raw_records=base.raw_records)

    def analyze_defrost(self,cycle:Any,*,equipment="iPro / Máquina"):
        phases={getattr(p.phase,"value",str(p.phase)):p for p in cycle.phases}; observations=[]
        for name in ("PRÉ-DEGELO","DEGELO","GOTEJAMENTO","RETORNO À REFRIGERAÇÃO","RECUPERAÇÃO"):
            p=phases.get(name); observations.append(f"{name}: {p.duration_seconds:.1f} s" if p else f"{name}: SEM DADOS")
        for t in cycle.temperatures:
            observations.append(f"{technician_label(t.variable_id)} - antes {display_value(t.before_average,'°C')}; durante {display_value(t.during_average,'°C')}; depois {display_value(t.after_average,'°C')}")
        status=getattr(cycle.status,"value",str(cycle.status))
        if status=="COMPLETO" and cycle.quality_score>=.8: result,hypothesis,confidence="DEGELO NORMAL","Ciclo completo conforme os marcadores observados.",.85
        elif status=="INCOMPLETO": result,hypothesis,confidence="DEGELO INCOMPLETO","Marcadores obrigatórios do ciclo não foram observados.",.75
        else: result,hypothesis,confidence="DADOS INSUFICIENTES","NÃO DETERMINADO",None
        first=self._from_row(cycle.first_deviation) if cycle.first_deviation else None
        return DiagnosticPresentation(equipment,cycle.session_id,"NÃO DETERMINADO",display_value(cycle.duration_seconds,"s"),result,result,first,
            f"Análise do ciclo de degelo: {result}.",tuple(observations),tuple(cycle.evidence_ids),(hypothesis,),
            "A recuperação térmica deve ser verificada quando incompleta ou anormal.",
            ("Verificar temperaturas, duração das fases, gotejamento e retorno à refrigeração.",),confidence)

    def _first_deviation(self,records,samples):
        explicit=next((r for r in records if str(r.get("kind","")).upper() in {"DESVIO","DEVIATION","ALARME","ALARM","PERDA DE COMUNICAÇÃO","COMMUNICATION_LOSS"}),None)
        if explicit:return self._from_row(explicit)
        previous={}
        for row in samples:
            variable=row.get("variable_id"); expected=(row.get("evidence") or {}).get("expected")
            if variable in previous and expected is not None and row.get("value")!=expected:return self._from_row(row,previous[variable],expected)
            previous[variable]=row
        return None

    def _from_row(self,row,previous=None,expected=None):
        value=row.get("value"); old=previous.get("value") if previous else row.get("previous_value",(row.get("evidence") or {}).get("previous_value"))
        difference=round(value-old,9) if isinstance(value,(int,float)) and isinstance(old,(int,float)) else None
        variable_id=row.get("variable_id") or row.get("name") or "não_determinado"; evidence_id=row.get("id")
        return FirstDeviation(str(row.get("timestamp") or "NÃO DETERMINADO"),variable_id,technician_label(variable_id),old,value,difference,
            display_value(expected) if expected is not None else str((row.get("evidence") or {}).get("expected","NÃO DETERMINADO")),
            row.get("message") or f"{technician_label(variable_id)}: {display_value(value)}",
            str((row.get("evidence") or {}).get("severity","ATENÇÃO")),(evidence_id,) if evidence_id is not None else ())

    def _phases(self,samples):
        latest=self._latest(samples,{"current_l1","current_l2","current_l3"})
        if len(latest)!=3 or not all(isinstance(r["value"],(int,float)) for r in latest.values()):return None
        values={k:float(r["value"]) for k,r in latest.items()}; average=fmean(values.values()); spread=max(values.values())-min(values.values()); ratio=spread/average if average else None
        if ratio is None or ratio<.10:return None
        deviated=max(values,key=lambda k:abs(values[k]-average)).split("_")[-1].upper(); severity="ANORMAL" if ratio>=.20 else "ATENÇÃO"
        observations=tuple(f"{k.split('_')[-1].upper()}: {v:g} A" for k,v in values.items())+(f"MAIOR DIFERENÇA: {spread:g} A",f"FASE MAIS DESVIADA: {deviated}",f"CONDIÇÃO: {severity}")
        evidence=tuple(r["id"] for r in latest.values() if r.get("id") is not None)
        return ("DESEQUILÍBRIO DE FASES","As correntes apresentaram diferença incompatível entre L1, L2 e L3.",observations,
            ("Possível desequilíbrio de corrente entre fases.",),"Possível condição anormal de alimentação elétrica.",
            ("Verificar alimentação elétrica, conexões, tensão entre fases, correntes e condição do equipamento.",),min(.90,.55+ratio),evidence)

    def _compressor(self,samples):
        latest=self._latest(samples,{"compressor_command","compressor"})
        if len(latest)!=2 or latest["compressor_command"].get("value") is not True or latest["compressor"].get("value") is not False:return None
        evidence=tuple(r["id"] for r in latest.values() if r.get("id") is not None)
        return ("COMANDO SEM CONFIRMAÇÃO DO COMPRESSOR","Existe comando para partida do compressor, porém o compressor não confirmou funcionamento.",
            ("COMANDO DO COMPRESSOR: LIGADO","ESTADO DO COMPRESSOR: DESLIGADO"),
            ("Proteção atuada.","Falha de partida.","Contato de potência ou proteção elétrica.","Condição externa impedindo partida."),
            "Refrigeração indisponível enquanto a partida não for confirmada.",
            ("Verificar proteções, circuito de potência, alimentação e intertravamentos externos.",),.85,evidence)

    @staticmethod
    def _latest(samples,wanted):
        result={}
        for row in samples:
            if row.get("variable_id") in wanted:result[row["variable_id"]]=row
        return result

    def _quality_ok(self,row):
        quality=row.get("quality");return not quality or str(quality).upper() in self.VALID_QUALITY
