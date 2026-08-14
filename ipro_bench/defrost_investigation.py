from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .time_utils import brasilia_text


FAMILY_DESCRIPTIONS = {
    "TEMPERATURE": "Comportamento térmico antes, durante e após o degelo.",
    "STATE": "Mudanças de estado e marcadores que delimitam as etapas do ciclo.",
    "ELECTRICAL": "Correntes e confirmações elétricas associadas aos atuadores.",
    "PRESSURE": "Pressões frigoríficas disponíveis durante a ocorrência.",
    "COMMUNICATION": "Qualidade e continuidade da aquisição dos dados.",
    "ALARM": "Alarmes e desvios registrados na janela investigada.",
}


@dataclass(frozen=True)
class DefrostInvestigation:
    session_id: str
    start: str
    end: str
    duration_seconds: float | None
    variables: tuple[str, ...]
    families: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    conclusion: str
    confidence: float | None
    confidence_reason: str
    reference: str


def investigate_defrost(cycle: Any, rows: Iterable[dict]) -> DefrostInvestigation:
    rows = tuple(dict(row) for row in rows)
    variables = tuple(sorted({str(row.get("variable_id")) for row in rows if row.get("variable_id")}))
    families = []
    if any("temp" in name.lower() for name in variables): families.append("TEMPERATURE")
    if any("pressure" in name.lower() for name in variables): families.append("PRESSURE")
    if any("current" in name.lower() for name in variables): families.append("ELECTRICAL")
    if getattr(cycle, "state_events", ()): families.append("STATE")
    if getattr(cycle, "alarms", ()): families.append("ALARM")
    if any(str(row.get("kind", "")).upper() == "PERDA DE COMUNICAÇÃO" for row in rows): families.append("COMMUNICATION")
    status = getattr(getattr(cycle, "status", None), "value", str(getattr(cycle, "status", "DADOS INSUFICIENTES")))
    quality = float(getattr(cycle, "quality_score", 0.0))
    completeness = 1.0 if status == "COMPLETO" else 0.55 if status == "INCOMPLETO" else 0.0
    coverage = min(1.0, len(families) / 4.0)
    confidence = None if not variables else min(0.95, 0.45 * quality + 0.35 * completeness + 0.20 * coverage)
    conclusion = "DEGELO NORMAL" if status == "COMPLETO" and quality >= 0.8 else "DEGELO INCOMPLETO" if status == "INCOMPLETO" else "DADOS INSUFICIENTES"
    start_ns, end_ns = getattr(cycle, "start_ns", None), getattr(cycle, "end_ns", None)
    timestamp_by_ns = {row.get("timestamp_ns"): row.get("timestamp") for row in rows}
    return DefrostInvestigation(
        cycle.session_id,
        brasilia_text(timestamp_by_ns.get(start_ns)) if timestamp_by_ns.get(start_ns) else "NÃO DETERMINADO",
        brasilia_text(timestamp_by_ns.get(end_ns)) if timestamp_by_ns.get(end_ns) else "NÃO DETERMINADO",
        getattr(cycle, "duration_seconds", None), variables, tuple(families), tuple(getattr(cycle, "evidence_ids", ())),
        conclusion, confidence,
        f"qualidade {quality:.0%}; ciclo {status.lower()}; {len(families)} família(s) de evidência disponível(is).",
        "Marcadores do ciclo, amostras válidas e relações temporais da própria sessão.",
    )
