from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Any

from .field_diagnostics import BlackBoxStore, TimelineKind


@dataclass(frozen=True)
class ExtractedFact:
    name: str
    evidence_ids: tuple[int, ...]
    first_timestamp: str
    details: dict[str, Any]
    description: str
    family: str


@dataclass(frozen=True)
class SessionInterpretation:
    session_id: str
    state: str
    quality: float
    sample_count: int
    facts: tuple[ExtractedFact, ...]
    variables: tuple[str, ...]
    explanation: str


class SessionEvidenceInterpreter:
    """Evidence-family analysis using only persisted samples, quality and state events."""
    PHASE_THRESHOLD=.10;MIN_PHASE_AVERAGE_AMPS=.50;MIN_SAMPLES=20

    def __init__(self,store:BlackBoxStore)->None:self.store=store
    def resolve(self,identifier:str)->str:return self.store.resolve_session_id(identifier)
    def facts(self,identifier:str)->dict[str,tuple[int,...]]:return {f.name:f.evidence_ids for f in self.extract(identifier)}
    def extract(self,identifier:str)->tuple[ExtractedFact,...]:return self.interpret(identifier).facts

    def interpret(self,identifier:str)->SessionInterpretation:
        session_id=self.resolve(identifier);rows=self.store.query(session_id);samples=[r for r in rows if r["kind"]==TimelineKind.SAMPLE.value]
        valid=[r for r in samples if self._valid(r)];quality=len(valid)/len(samples) if samples else 0.0;variables=tuple(sorted({r["variable_id"] for r in samples if r.get("variable_id")}))
        if not samples:return SessionInterpretation(session_id,"SEM DADOS",0.0,0,(),(),"A sessão não contém amostras.")
        if len(samples)<self.MIN_SAMPLES:return SessionInterpretation(session_id,"DADOS INSUFICIENTES",quality,len(samples),(),variables,"Existem amostras, mas a cobertura temporal é insuficiente.")
        groups={}
        for row in samples:groups.setdefault(row["timestamp_ns"],{})[row.get("variable_id")]=row
        facts=[]
        facts.extend(self._phase(groups));facts.extend(self._compressor(groups));facts.extend(self._fan(groups));facts.extend(self._sensor(samples));facts.extend(self._communication(rows,samples));facts.extend(self._defrost(rows,samples));facts.extend(self._recovery(rows,samples));facts.extend(self._high_current(samples))
        facts=tuple(self._unique(facts))
        state="ANOMALIA DETECTADA" if facts else "SEM ANOMALIA"
        explanation=(f"{len(facts)} relação(ões) anormais sustentada(s) por registros da sessão." if facts else "Dados suficientes; nenhuma relação anormal configurada foi observada.")
        return SessionInterpretation(session_id,state,quality,len(samples),facts,variables,explanation)

    def evidence_text(self,fact:ExtractedFact)->str:
        return f"Evidência {', '.join('E'+str(i) for i in fact.evidence_ids)}: {fact.description}"

    def _phase(self,groups):
        for group in groups.values():
            rows=[group.get(k) for k in ("current_l1","current_l2","current_l3")]
            if all(r and isinstance(r.get("value"),(int,float)) and self._valid(r) for r in rows):
                values=[float(r["value"]) for r in rows];avg=fmean(values);spread=max(values)-min(values)
                if avg>=self.MIN_PHASE_AVERAGE_AMPS and spread/avg>=self.PHASE_THRESHOLD:
                    phase=max(range(3),key=lambda i:abs(values[i]-avg))+1;ids=tuple(r["id"] for r in rows)
                    yield ExtractedFact("phase_current_imbalance",ids,rows[0]["timestamp"],{"values":values,"ratio":spread/avg,"observed":values[phase-1],"reference":avg},f"L1={values[0]:.2f} A, L2={values[1]:.2f} A e L3={values[2]:.2f} A no mesmo instante; diferença relativa {spread/avg:.1%}.","ELÉTRICA")
                    return

    def _compressor(self,groups):
        consecutive=[]
        for group in groups.values():
            command,feedback,current=group.get("compressor_command"),group.get("compressor"),group.get("current_compressor")
            if command and feedback and command.get("value") is True and feedback.get("value") is False and self._valid(command) and self._valid(feedback):consecutive.append((command,feedback,current))
            else:consecutive=[]
            if len(consecutive)>=2:
                first,last=consecutive[0],consecutive[-1];ids=tuple(dict.fromkeys(r["id"] for item in (first,last) for r in item if r))
                yield ExtractedFact("compressor_command_without_feedback",ids,first[0]["timestamp"],{"observed":0.0,"reference":1.0},"Comando do compressor LIGADO e retorno DESLIGADO em amostras consecutivas; corrente associada preservada.","COMPRESSOR");return

    def _fan(self,groups):
        matches=[]
        for group in groups.values():
            fan=group.get("condenser_fan");state=self._metadata(fan).get("machine_state") if fan else None
            operational=bool(state) and (str(state).upper().startswith("EST") or "RESFRIAMENTO" in str(state).upper() or "RECUP" in str(state).upper())
            if fan and operational and fan.get("value") is False and self._valid(fan):matches.append(fan)
            else:matches=[]
            if len(matches)>=2:
                ids=(matches[0]["id"],matches[-1]["id"]);yield ExtractedFact("condenser_fan_without_feedback",ids,matches[0]["timestamp"],{"observed":0.0,"reference":1.0},"Ventilador do condensador permaneceu DESLIGADO durante estado operacional que solicita rejeição de calor.","VENTILADOR");return

    def _sensor(self,samples):
        bad=[r for r in samples if r.get("variable_id")=="temperature_chamber" and (r.get("value") is None or not self._valid(r))]
        if bad:
            ids=tuple(r["id"] for r in bad[:3]);yield ExtractedFact("invalid_sensor_reading",ids,bad[0]["timestamp"],{"observed":0.0,"reference":1.0},"Temperatura da câmara sem valor válido e com qualidade inadequada em registros consecutivos.","SENSOR")

    def _communication(self,rows,samples):
        events=[r for r in rows if r["kind"]==TimelineKind.COMMUNICATION_LOSS.value];lost=[r for r in samples if r.get("variable_id")=="communication" and r.get("value") is False]
        if events or lost:
            selected=(events[:1]+lost[:2]);yield ExtractedFact("communication_loss_observed",tuple(r["id"] for r in selected),selected[0]["timestamp"],{"observed":0.0,"reference":1.0},"Evento de perda de comunicação e/ou amostras de comunicação DESLIGADA foram registrados.","COMUNICAÇÃO")

    def _defrost(self,rows,samples):
        markers={r["name"]:r for r in rows if r["kind"]==TimelineKind.MARKER.value};start,end=markers.get("DEGELO_INICIO"),markers.get("DEGELO_FIM")
        if not start:return
        required=("DEGELO_FIM","GOTEJAMENTO_FIM","RETORNO_REFRIGERACAO");missing=[name for name in required if name not in markers]
        temps=[r for r in samples if r.get("variable_id")=="temperature_evaporator" and start["timestamp_ns"]<=r["timestamp_ns"]<=(end["timestamp_ns"] if end else 10**30) and isinstance(r.get("value"),(int,float))]
        rise=(float(temps[-1]["value"])-float(temps[0]["value"])) if len(temps)>=2 else None
        if missing or rise is None or rise<2.0:
            selected=[start,*([end] if end else []),*([temps[0],temps[-1]] if len(temps)>=2 else [])];ids=tuple(dict.fromkeys(r["id"] for r in selected))
            rise_text="não determinada" if rise is None else f"{rise:.2f}".replace(".",",")
            yield ExtractedFact("incomplete_defrost_cycle",ids,start["timestamp"],{"observed":rise,"reference":2.0,"missing":missing},f"Ciclo de degelo com marcadores ausentes {missing or 'nenhum'}; elevação do evaporador {rise_text} °C.","DEGELO")

    def _recovery(self,rows,samples):
        marker=next((r for r in rows if r["kind"]==TimelineKind.MARKER.value and r["name"]=="RETORNO_REFRIGERACAO"),None)
        if not marker:return
        temps=[r for r in samples if r.get("variable_id")=="temperature_chamber" and r["timestamp_ns"]>=marker["timestamp_ns"] and isinstance(r.get("value"),(int,float))]
        if len(temps)>=3:
            drop=float(temps[0]["value"])-float(temps[-1]["value"]);duration=(temps[-1]["timestamp_ns"]-temps[0]["timestamp_ns"])/1e9
            if duration>=120 and drop<1.0:
                yield ExtractedFact("slow_thermal_recovery",(marker["id"],temps[0]["id"],temps[-1]["id"]),marker["timestamp"],{"observed":drop,"reference":1.0},f"Após retorno à refrigeração, temperatura da câmara reduziu apenas {drop:.2f} °C em {duration:.0f} s.","RECUPERAÇÃO")

    def _high_current(self,samples):
        high=[r for r in samples if r.get("variable_id")=="current_compressor" and isinstance(r.get("value"),(int,float)) and float(r["value"])>=18 and self._valid(r) and "PARTIDA" not in str(self._metadata(r).get("machine_state","")).upper()]
        if len(high)>=2:
            yield ExtractedFact("high_compressor_current",(high[0]["id"],high[-1]["id"]),high[0]["timestamp"],{"observed":fmean(float(r["value"]) for r in high),"reference":18.0},f"Corrente do compressor permaneceu acima de 18 A; média observada {fmean(float(r['value']) for r in high):.2f} A.","COMPRESSOR")

    @staticmethod
    def _valid(row):return str(row.get("quality","")).upper() in {"VÁLIDA","VALID","GOOD"}
    @staticmethod
    def _metadata(row):return (row.get("evidence") or {}).get("metadata",{})
    @staticmethod
    def _unique(facts):
        seen=set()
        for fact in facts:
            if fact.name not in seen:seen.add(fact.name);yield fact
