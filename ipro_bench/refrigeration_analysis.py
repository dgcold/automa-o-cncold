from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from refrigerantes import calcular_subresfriamento_c, calcular_superaquecimento_c


class ReadingStatus(StrEnum):
    NORMAL = "NORMAL"
    ATTENTION = "ATENÇÃO"
    INSUFFICIENT = "DADOS INSUFICIENTES"


@dataclass(frozen=True)
class ThermalReading:
    name: str
    pressure_psig: float | None
    line_temperature_c: float | None
    saturation_temperature_c: float | None
    value_c: float | None
    status: ReadingStatus
    quality: float
    reference: str


@dataclass(frozen=True)
class RefrigerationAssessment:
    hypothesis: str
    evidence: tuple[str, ...]
    confidence: float | None
    confidence_reason: str
    alternatives: tuple[str, ...]
    technician_checks: tuple[str, ...]


class RefrigerationAnalyzer:
    """Deterministic refrigeration calculations; never confirms a physical leak."""

    def __init__(
        self,
        superheat_calculator: Callable = calcular_superaquecimento_c,
        subcooling_calculator: Callable = calcular_subresfriamento_c,
    ) -> None:
        self._superheat = superheat_calculator
        self._subcooling = subcooling_calculator

    def superheat(self, pressure_psig, suction_temperature_c, refrigerant: str) -> ThermalReading:
        return self._reading("SUPERAQUECIMENTO", pressure_psig, suction_temperature_c, refrigerant, True)

    def subcooling(self, pressure_psig, liquid_temperature_c, refrigerant: str) -> ThermalReading:
        return self._reading("SUBRESFRIAMENTO", pressure_psig, liquid_temperature_c, refrigerant, False)

    def _reading(self, name, pressure, temperature, refrigerant, superheat) -> ThermalReading:
        if not isinstance(pressure, (int, float)) or not isinstance(temperature, (int, float)):
            return ThermalReading(name, pressure, temperature, None, None, ReadingStatus.INSUFFICIENT, 0.0,
                                  "Pressão e temperatura de linha válidas são obrigatórias.")
        value, saturation = (self._superheat if superheat else self._subcooling)(pressure, temperature, refrigerant)
        if value is None or saturation is None:
            return ThermalReading(name, float(pressure), float(temperature), None, None, ReadingStatus.INSUFFICIENT,
                                  0.5, "Curva de saturação indisponível para o refrigerante selecionado.")
        low, high = ((4.0, 12.0) if superheat else (3.0, 10.0))
        status = ReadingStatus.NORMAL if low <= value <= high else ReadingStatus.ATTENTION
        return ThermalReading(name, float(pressure), float(temperature), saturation, value, status, 1.0,
                              f"Faixa técnica configurada: {low:.1f} a {high:.1f} °C; comparar com documentação do equipamento.")

    def assess_charge(self, superheat: ThermalReading, subcooling: ThermalReading,
                      *, suction_pressure_psig: float | None = None) -> RefrigerationAssessment:
        available = [item for item in (superheat, subcooling) if item.value_c is not None]
        if len(available) < 2:
            return RefrigerationAssessment("DADOS INSUFICIENTES", (), None,
                "Superaquecimento e subresfriamento válidos são necessários.",
                ("Restrição", "Fluxo de ar", "Válvula de expansão", "Condição operacional"),
                ("Confirmar refrigerante, pressões e temperaturas com instrumentos calibrados.",))
        evidence = []
        if superheat.value_c > 12.0: evidence.append(f"Superaquecimento elevado: {superheat.value_c:.2f} °C")
        if subcooling.value_c < 3.0: evidence.append(f"Subresfriamento baixo: {subcooling.value_c:.2f} °C")
        if suction_pressure_psig is not None and suction_pressure_psig < 20.0:
            evidence.append(f"Pressão de sucção baixa no contexto configurado: {suction_pressure_psig:.2f} psig")
        coherent = superheat.value_c > 12.0 and subcooling.value_c < 3.0
        confidence = min(0.90, 0.45 + 0.12 * len(evidence)) if coherent else min(0.65, 0.35 + 0.08 * len(evidence))
        hypothesis = "POSSÍVEL CARGA INSUFICIENTE / POSSÍVEL VAZAMENTO" if coherent else "PADRÃO NÃO CONCLUSIVO"
        reason = f"{len(evidence)} evidência(s) coerente(s); qualidade combinada {min(superheat.quality, subcooling.quality):.0%}."
        return RefrigerationAssessment(hypothesis, tuple(evidence), confidence, reason,
            ("Restrição ou filtro secador", "Alimentação da válvula de expansão", "Fluxo de ar insuficiente", "Carga térmica e condição de operação"),
            ("Verificar vazamentos fisicamente; não concluir pela telemetria.", "Medir pressões e temperaturas estabilizadas.",
             "Inspecionar filtro secador, válvula de expansão e fluxo de ar."))
