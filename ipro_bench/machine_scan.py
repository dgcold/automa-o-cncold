from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

from .refrigeration_analysis import RefrigerationAnalyzer, ThermalReading
from refrigerantes import PRESSAO_ATMOSFERICA_PSI, PSI_PARA_PA, REFRIGERANTES, temperatura_saturacao_c


ENGINEERING_SOURCE = "CÁLCULO DE ENGENHARIA"


class ScanStatus(StrEnum):
    NORMAL = "NORMAL"
    DEVIATION = "DESVIO"
    NOT_ANALYZED = "NÃO ANALISADO"
    INSUFFICIENT = "DADOS INSUFICIENTES"


class ReferenceStatus(StrEnum):
    EXACT = "REFERÊNCIA DE ENGENHARIA"
    INTERPOLATED = "REFERÊNCIA INTERPOLADA"
    OUTSIDE_ENVELOPE = "FORA DO ENVELOPE DE REFERÊNCIA DE ENGENHARIA"
    INSUFFICIENT = "DADOS DE ENGENHARIA INSUFICIENTES"


class RefrigerantState(StrEnum):
    SUBCOOLED_LIQUID = "LÍQUIDO SUBRESFRIADO"
    SATURATION = "REGIÃO DE SATURAÇÃO / POSSÍVEL BIFÁSICO"
    SUPERHEATED_VAPOR = "VAPOR SUPERAQUECIDO"
    UNDETERMINED = "ESTADO NÃO DETERMINADO — DADOS INSUFICIENTES"


@dataclass(frozen=True)
class EngineeringValue:
    name: str
    value: float | bool | str | None
    unit: str = ""
    operating_condition: str = ""
    source: str = ENGINEERING_SOURCE
    version_date: str | None = None


@dataclass(frozen=True)
class EngineeringPoint:
    id: str
    chamber_temperature_c: float
    values: dict[str, EngineeringValue]
    condition: str = ""
    version_date: str | None = None

    @classmethod
    def create(cls, identifier: str, chamber_temperature_c: float, values: dict[str, Any], **kwargs):
        converted = {
            name: value if isinstance(value, EngineeringValue) else EngineeringValue(name, value)
            for name, value in values.items()
        }
        return cls(identifier, float(chamber_temperature_c), converted, **kwargs)


@dataclass(frozen=True)
class ReferenceSelection:
    status: ReferenceStatus
    point_ids: tuple[str, ...]
    chamber_temperature_c: float
    values: dict[str, EngineeringValue]
    message: str


@dataclass(frozen=True)
class Measurement:
    name: str
    value: float | bool | str | None
    unit: str = ""
    timestamp: str | None = None
    quality: str | float = "VÁLIDA"
    source: str = "VALOR MEDIDO"
    evidence_ids: tuple[int, ...] = ()

    @property
    def valid(self) -> bool:
        if isinstance(self.quality, (int, float)) and not isinstance(self.quality, bool):
            return self.value is not None and float(self.quality) >= 0.8
        quality = str(self.quality).strip().upper()
        return self.value is not None and quality in {"VÁLIDA", "VALIDA", "VALID", "GOOD", "1.0"}


@dataclass(frozen=True)
class Deviation:
    name: str
    engineering_value: float
    measured_value: float
    value: float
    unit: str


@dataclass(frozen=True)
class ScanStage:
    id: str
    name: str
    status: ScanStatus
    engineering: tuple[EngineeringValue, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    deviations: tuple[Deviation, ...] = ()
    evidence_ids: tuple[int, ...] = ()
    hypothesis: str = "NÃO DETERMINADA"
    recommendations: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipeInput:
    outer_diameter_m: float | None = None
    wall_thickness_m: float | None = None
    straight_length_m: float | None = None
    fittings_equivalent_length_m: float = 0.0
    mass_flow_kg_s: float | None = None
    density_kg_m3: float | None = None
    friction_factor: float | None = None
    elevation_m: float = 0.0
    refrigerant_state: RefrigerantState = RefrigerantState.UNDETERMINED


@dataclass(frozen=True)
class PipeResult:
    applicable: bool
    message: str
    internal_diameter_m: float | None = None
    area_m2: float | None = None
    velocity_m_s: float | None = None
    equivalent_length_m: float | None = None
    friction_pressure_drop_pa: float | None = None
    elevation_pressure_drop_pa: float | None = None
    total_pressure_drop_pa: float | None = None


@dataclass(frozen=True)
class ThermodynamicPoint:
    name: str
    refrigerant: str | None
    pressure_gauge: float | None
    pressure_unit: str
    pressure_gauge_psig: float | None
    pressure_absolute_pa: float | None
    saturation_temperature_c: float | None
    measured_temperature_c: float | None
    superheat_k: float | None
    status: str
    message: str


@dataclass(frozen=True)
class MachineScanResult:
    id: str
    session_id: str | None
    execution_id: str | None
    created_at: str
    reference: ReferenceSelection
    measurements: tuple[Measurement, ...]
    deviations: tuple[Deviation, ...]
    stages: tuple[ScanStage, ...]
    first_deviation: str | None
    deviation_location: str
    diagnosis: str
    primary_hypothesis: str
    evidence_ids: tuple[int, ...]
    missing_measurements: tuple[str, ...]
    recommendations: tuple[str, ...]
    confidence: float | None
    confidence_reason: str
    preliminary_stage: ScanStatus = ScanStatus.NOT_ANALYZED
    evaluated_stage_count: int = 0
    localization_reason: str = "NÃO DETERMINADO"
    missing_measurements_purpose: str = ""
    thermodynamic_note: str = ""
    thermodynamic_points: tuple[ThermodynamicPoint, ...] = ()
    continuation_requirement: str = ""
    specialized_results: dict[str, Any] = field(default_factory=dict)
    technician_decision: str | None = None


STAGE_ORDER = (
    ("condenser", "CONDENSADOR"),
    ("liquid_line", "LINHA DE LÍQUIDO"),
    ("expansion_valve", "VÁLVULA DE EXPANSÃO"),
    ("evaporator", "EVAPORADOR / SERPENTINA ALETADA"),
    ("suction_line", "LINHA DE SUCÇÃO"),
    ("compressor", "COMPRESSOR"),
    ("discharge_line", "LINHA DE DESCARGA"),
    ("electrical", "PARTE ELÉTRICA"),
    ("controls", "CONTROLES / AUTOMAÇÃO"),
)


ALIASES = {
    "chamber_temperature_c": ("chamber_temperature_c", "temperature_chamber"),
    "evaporation_temperature_c": ("evaporation_temperature_c", "temperature_evaporation"),
    "evaporator_outlet_pressure": ("evaporator_outlet_pressure", "pressure_evaporator_outlet"),
    "compressor_inlet_pressure": ("compressor_inlet_pressure", "pressure_suction", "pressure_compressor_inlet"),
    "evaporator_outlet_temperature_c": ("evaporator_outlet_temperature_c", "temperature_evaporator_outlet"),
    "compressor_inlet_temperature_c": ("compressor_inlet_temperature_c", "temperature_suction"),
    "condenser_outlet_subcooling_k": ("condenser_outlet_subcooling_k", "subcooling_condenser_outlet"),
    "valve_inlet_subcooling_k": ("valve_inlet_subcooling_k", "subcooling_valve_inlet"),
}


def select_engineering_reference(points: Iterable[EngineeringPoint], chamber_temperature_c: float) -> ReferenceSelection:
    points = tuple(sorted(points, key=lambda item: item.chamber_temperature_c))
    if not points:
        return ReferenceSelection(ReferenceStatus.INSUFFICIENT, (), chamber_temperature_c, {}, "Nenhum ponto de engenharia cadastrado.")
    exact = next((p for p in points if math.isclose(p.chamber_temperature_c, chamber_temperature_c, abs_tol=1e-9)), None)
    if exact:
        return ReferenceSelection(ReferenceStatus.EXACT, (exact.id,), chamber_temperature_c, exact.values, "Ponto de operação compatível.")
    if chamber_temperature_c < points[0].chamber_temperature_c or chamber_temperature_c > points[-1].chamber_temperature_c:
        return ReferenceSelection(ReferenceStatus.OUTSIDE_ENVELOPE, (), chamber_temperature_c, {}, "Não houve extrapolação silenciosa.")
    lower, upper = next((a, b) for a, b in zip(points, points[1:]) if a.chamber_temperature_c < chamber_temperature_c < b.chamber_temperature_c)
    ratio = (chamber_temperature_c - lower.chamber_temperature_c) / (upper.chamber_temperature_c - lower.chamber_temperature_c)
    values: dict[str, EngineeringValue] = {}
    for name in lower.values.keys() & upper.values.keys():
        a, b = lower.values[name], upper.values[name]
        if isinstance(a.value, (int, float)) and not isinstance(a.value, bool) and isinstance(b.value, (int, float)) and not isinstance(b.value, bool) and a.unit == b.unit:
            values[name] = EngineeringValue(name, float(a.value) + ratio * (float(b.value) - float(a.value)), a.unit, "REFERÊNCIA INTERPOLADA", ENGINEERING_SOURCE, a.version_date or b.version_date)
    return ReferenceSelection(ReferenceStatus.INTERPOLATED, (lower.id, upper.id), chamber_temperature_c, values, "Valores numéricos comuns interpolados; não são medições.")


def calculate_pipe(data: PipeInput) -> PipeResult:
    if data.refrigerant_state is RefrigerantState.SATURATION:
        return PipeResult(False, "Cálculo simplificado não aplicável em região bifásica.")
    required = (data.outer_diameter_m, data.wall_thickness_m, data.straight_length_m, data.mass_flow_kg_s, data.density_kg_m3, data.friction_factor)
    if any(value is None for value in required):
        return PipeResult(False, "DADOS INSUFICIENTES para o cálculo de tubulação.")
    outer, wall, length, flow, density, friction = map(float, required)
    internal = outer - 2 * wall
    if internal <= 0 or length < 0 or flow < 0 or density <= 0 or friction < 0 or data.fittings_equivalent_length_m < 0:
        return PipeResult(False, "Dados de tubulação inválidos.")
    area = math.pi * internal**2 / 4
    velocity = flow / (density * area)
    equivalent = length + data.fittings_equivalent_length_m
    friction_drop = friction * (equivalent / internal) * (density * velocity**2 / 2)
    elevation_drop = density * 9.80665 * data.elevation_m
    return PipeResult(True, "Cálculo monofásico simplificado.", internal, area, velocity, equivalent, friction_drop, elevation_drop, friction_drop + elevation_drop)


def classify_refrigerant_state(reading: ThermalReading, tolerance_c: float = 1.0) -> RefrigerantState:
    if reading.saturation_temperature_c is None or reading.line_temperature_c is None:
        return RefrigerantState.UNDETERMINED
    delta = reading.line_temperature_c - reading.saturation_temperature_c
    if abs(delta) <= tolerance_c:
        return RefrigerantState.SATURATION
    return RefrigerantState.SUPERHEATED_VAPOR if reading.name == "SUPERAQUECIMENTO" and delta > 0 else RefrigerantState.SUBCOOLED_LIQUID if reading.name == "SUBRESFRIAMENTO" and delta < 0 else RefrigerantState.UNDETERMINED


def pressure_to_psig(value: float, unit: str) -> float | None:
    normalized = unit.strip().upper().replace(" ", "")
    factors = {"PSIG": 1.0, "BAR(G)": 14.5037738, "BARG": 14.5037738, "KPA(G)": 0.145037738, "KPAG": 0.145037738}
    factor = factors.get(normalized)
    if factor is None or not math.isfinite(float(value)):
        return None
    pressure_psig = float(value) * factor
    return pressure_psig if pressure_psig + PRESSAO_ATMOSFERICA_PSI > 0 else None


def pressure_absolute_pa(value: float, unit: str) -> float | None:
    pressure_psig = pressure_to_psig(value, unit)
    return None if pressure_psig is None else (pressure_psig + PRESSAO_ATMOSFERICA_PSI) * PSI_PARA_PA


def saturation_from_pressure(measurement: Measurement, refrigerant: str | None) -> float | None:
    if not refrigerant or not measurement.valid or not isinstance(measurement.value, (int, float)):
        return None
    pressure_psig = pressure_to_psig(float(measurement.value), measurement.unit)
    return None if pressure_psig is None else temperatura_saturacao_c(pressure_psig, refrigerant, qualidade=1)


def thermodynamic_point(name: str, pressure: Measurement | None, temperature: Measurement | None,
                        refrigerant: str | None) -> ThermodynamicPoint:
    measured_temperature = float(temperature.value) if temperature and temperature.valid and isinstance(temperature.value, (int, float)) else None
    if not pressure or not pressure.valid or not isinstance(pressure.value, (int, float)):
        return ThermodynamicPoint(name, refrigerant, None, pressure.unit if pressure else "", None, None, None, measured_temperature, None, "DADOS INSUFICIENTES", "Pressão válida não informada.")
    gauge = float(pressure.value); psig = pressure_to_psig(gauge, pressure.unit); absolute = pressure_absolute_pa(gauge, pressure.unit)
    if psig is None or absolute is None:
        return ThermodynamicPoint(name, refrigerant, gauge, pressure.unit, None, None, None, measured_temperature, None, "PRESSÃO INVÁLIDA", "Unidade desconhecida, valor não finito ou pressão absoluta não positiva.")
    if refrigerant not in REFRIGERANTES:
        return ThermodynamicPoint(name, refrigerant, gauge, pressure.unit, psig, absolute, None, measured_temperature, None, "REFRIGERANTE NÃO CONFIRMADO", "Refrigerante ausente ou não confirmado na configuração do projeto.")
    saturation = temperatura_saturacao_c(psig, refrigerant, qualidade=1)
    if saturation is None:
        return ThermodynamicPoint(name, refrigerant, gauge, pressure.unit, psig, absolute, None, measured_temperature, None, "PROPRIEDADES INDISPONÍVEIS", "Modelo termodinâmico indisponível para a condição informada.")
    superheat = None if measured_temperature is None else measured_temperature - saturation
    return ThermodynamicPoint(name, refrigerant, gauge, pressure.unit, psig, absolute, saturation, measured_temperature, superheat, "CALCULADO", "Conversão manométrica → absoluta → saturação rastreada sem tabela aproximada.")


class MachineScanAnalyzer:
    """Localiza o primeiro desvio observável sem promover hipótese a causa-raiz."""

    def __init__(self, refrigeration: RefrigerationAnalyzer | None = None, tolerance: float = 1.0):
        self.refrigeration = refrigeration or RefrigerationAnalyzer()
        self.tolerance = tolerance

    def analyze(self, points: Iterable[EngineeringPoint], measurements: Iterable[Measurement], *, session_id: str | None = None,
                execution_id: str | None = None, specialized_results: dict[str, Any] | None = None,
                refrigerant: str | None = None) -> MachineScanResult:
        measurements = tuple(measurements)
        indexed = {m.name: m for m in measurements}
        chamber = self._measurement(indexed, "chamber_temperature_c")
        if not chamber or not chamber.valid or not self._number(chamber.value):
            reference = ReferenceSelection(ReferenceStatus.INSUFFICIENT, (), 0.0, {}, "Temperatura da câmara válida é necessária para selecionar a referência.")
            return self._inconclusive(reference, measurements, session_id, execution_id, ("temperatura da câmara",), specialized_results)
        reference = select_engineering_reference(points, float(chamber.value))
        if not reference.values:
            return self._inconclusive(reference, measurements, session_id, execution_id, ("referência de engenharia compatível",), specialized_results)

        deviations: list[Deviation] = []
        expected_evap = reference.values.get("evaporation_temperature_c")
        observed_evap = self._measurement(indexed, "evaporation_temperature_c")
        if expected_evap and self._number(expected_evap.value) and observed_evap and observed_evap.valid and self._number(observed_evap.value):
            deviations.append(Deviation("TEMPERATURA DE EVAPORAÇÃO", float(expected_evap.value), float(observed_evap.value), float(observed_evap.value)-float(expected_evap.value), "K"))
            expected_td = float(chamber.value)-float(expected_evap.value)
            observed_td = float(chamber.value)-float(observed_evap.value)
            deviations.append(Deviation("TD", expected_td, observed_td, observed_td-expected_td, "K"))

        stages = {identifier: ScanStage(identifier, name, ScanStatus.NOT_ANALYZED) for identifier, name in STAGE_ORDER}
        missing: list[str] = []
        location = "NÃO DETERMINADA"
        hypothesis = "NÃO DETERMINADA"
        recommendations: tuple[str, ...] = ()
        first: str | None = None
        thermodynamic_note = ""
        continuation_requirement = ""

        evap_out = self._measurement(indexed, "evaporator_outlet_pressure")
        comp_in = self._measurement(indexed, "compressor_inlet_pressure")
        evap_out_temperature = self._measurement(indexed, "evaporator_outlet_temperature_c")
        comp_in_temperature = self._measurement(indexed, "compressor_inlet_temperature_c")
        thermodynamic_points = (
            thermodynamic_point("SAÍDA DO EVAPORADOR", evap_out, evap_out_temperature, refrigerant),
            thermodynamic_point("ENTRADA DO COMPRESSOR", comp_in, comp_in_temperature, refrigerant),
        )
        expected_out = reference.values.get("evaporator_outlet_pressure")
        if expected_out and self._number(expected_out.value):
            if not evap_out or not evap_out.valid or not self._number(evap_out.value): missing.append("pressão na saída do evaporador")
            if not comp_in or not comp_in.valid or not self._number(comp_in.value): missing.append("pressão na entrada do compressor")
            if not missing:
                out_delta = float(evap_out.value)-float(expected_out.value)
                comp_delta = float(comp_in.value)-float(expected_out.value)
                if abs(out_delta) <= self.tolerance and abs(comp_delta) >= self.tolerance:
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.NORMAL, (expected_out,), (evap_out,))
                    recommendations = ("Verificar diâmetro", "Verificar comprimento e comprimento equivalente", "Inspecionar curvas, acessórios e restrições", "Verificar desnível e perda de pressão")
                    hypothesis = "POSSÍVEL DESVIO NA LINHA DE SUCÇÃO"
                    location = "Entre saída do evaporador e entrada do compressor"
                    first = "LINHA DE SUCÇÃO"
                    stages["suction_line"] = self._stage("suction_line", ScanStatus.DEVIATION, (expected_out,), (evap_out, comp_in), hypothesis, recommendations)
                elif abs(out_delta) > self.tolerance:
                    recommendations = ("Verificar alimentação de refrigerante e válvula de expansão", "Cruzar superaquecimento e subresfriamento", "Verificar fluxo de ar, ventiladores, gelo e sujeira", "Inspecionar distribuição de refrigerante e serpentina")
                    hypothesis = "DESVIO PRESENTE NO EVAPORADOR OU ANTES DELE"
                    location = "Evaporador ou circuito a montante"
                    first = "VÁLVULA DE EXPANSÃO / EVAPORADOR"
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.DEVIATION, (expected_out,), (evap_out,), hypothesis, recommendations)
                else:
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.NORMAL, (expected_out,), (evap_out,))
                    stages["suction_line"] = self._stage("suction_line", ScanStatus.NORMAL, (expected_out,), (evap_out, comp_in))

        # Quando não existe referência de pressão, compara condições equivalentes
        # somente se refrigerante, unidade e propriedades termodinâmicas forem válidos.
        if not expected_out and expected_evap and evap_out and comp_in and evap_out.valid and comp_in.valid:
            outlet_sat = thermodynamic_points[0].saturation_temperature_c
            compressor_sat = thermodynamic_points[1].saturation_temperature_c
            if outlet_sat is None or compressor_sat is None:
                thermodynamic_note = "Pressões registradas, mas não foi possível convertê-las em temperatura de saturação com segurança. Informe refrigerante válido, unidade manométrica conhecida e disponibilize propriedades termodinâmicas."
                continuation_requirement = "Disponibilizar propriedades termodinâmicas válidas do refrigerante para conversão P/T."
            else:
                expected_temperature = float(expected_evap.value)
                outlet_delta = outlet_sat - expected_temperature
                compressor_delta = compressor_sat - expected_temperature
                if abs(outlet_delta) <= self.tolerance and abs(compressor_delta) > self.tolerance:
                    recommendations = ("Verificar diâmetro", "Verificar comprimento e comprimento equivalente", "Inspecionar curvas, acessórios e restrições", "Verificar desnível e perda de pressão")
                    hypothesis = "POSSÍVEL DESVIO NA LINHA DE SUCÇÃO"
                    location = "Entre saída do evaporador e entrada do compressor"
                    first = "LINHA DE SUCÇÃO"
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.NORMAL, (), (evap_out,))
                    stages["suction_line"] = self._stage("suction_line", ScanStatus.DEVIATION, (), (evap_out, comp_in), hypothesis, recommendations)
                elif abs(outlet_delta) > self.tolerance:
                    recommendations = ("Verificar alimentação de refrigerante e válvula de expansão", "Cruzar superaquecimento e subresfriamento", "Verificar fluxo de ar, ventiladores, gelo e sujeira")
                    hypothesis = "DESVIO PRESENTE NO EVAPORADOR OU ALIMENTAÇÃO"
                    location = "EVAPORADOR / ALIMENTAÇÃO"
                    first = "EVAPORADOR / ALIMENTAÇÃO"
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.DEVIATION, (), (evap_out,), hypothesis, recommendations)
                else:
                    stages["evaporator"] = self._stage("evaporator", ScanStatus.NORMAL, (), (evap_out,))
                    stages["suction_line"] = self._stage("suction_line", ScanStatus.NORMAL, (), (evap_out, comp_in))
                thermodynamic_note = f"Conversão termodinâmica aplicada com {refrigerant}: saída do evaporador {outlet_sat:.2f} °C; entrada do compressor {compressor_sat:.2f} °C de saturação equivalente."

        condenser_sc = self._measurement(indexed, "condenser_outlet_subcooling_k")
        valve_sc = self._measurement(indexed, "valve_inlet_subcooling_k")
        if condenser_sc and valve_sc and condenser_sc.valid and valve_sc.valid and self._number(condenser_sc.value) and self._number(valve_sc.value):
            loss = float(condenser_sc.value)-float(valve_sc.value)
            if loss > self.tolerance:
                liquid_hypothesis = "POSSÍVEL PERDA NA LINHA DE LÍQUIDO"
                checks = ("Verificar pressão antes da válvula", "Verificar filtro secador e possível restrição", "Verificar diâmetro, comprimento, acessórios e desnível")
                stages["liquid_line"] = self._stage("liquid_line", ScanStatus.DEVIATION, (), (condenser_sc, valve_sc), liquid_hypothesis, checks)
                if first is None:
                    first, location, hypothesis, recommendations = "LINHA DE LÍQUIDO", "Entre condensador e válvula de expansão", liquid_hypothesis, checks
            else:
                stages["liquid_line"] = self._stage("liquid_line", ScanStatus.NORMAL, (), (condenser_sc, valve_sc))

        thermal_deviation = bool(deviations and any(abs(d.value) > self.tolerance for d in deviations))
        preliminary = ScanStatus.DEVIATION if thermal_deviation else ScanStatus.NORMAL if deviations else ScanStatus.INSUFFICIENT
        localization_reason = "O primeiro ponto físico com desvio foi identificado."
        purpose = ""
        if thermal_deviation and not first:
            first, location, hypothesis = "NÃO LOCALIZADO", "NÃO DETERMINADA", "DIAGNÓSTICO INCONCLUSIVO"
            localization_reason = "Faltam medições entre evaporador e compressor."
            priority = (
                ("evaporator_outlet_pressure", "pressão na saída do evaporador"),
                ("evaporator_outlet_temperature_c", "temperatura na saída do evaporador"),
                ("compressor_inlet_pressure", "pressão na entrada do compressor"),
                ("compressor_inlet_temperature_c", "temperatura na entrada do compressor"),
            )
            missing.extend(label for key, label in priority if not (self._measurement(indexed, key) and self._measurement(indexed, key).valid))
            if missing:
                purpose = "Essas medições são necessárias para determinar se a queda de pressão/temperatura equivalente já ocorre no evaporador ou se aparece entre a saída do evaporador e a entrada do compressor."
            elif thermodynamic_note:
                localization_reason = "Medições disponíveis, porém conversão pressão → temperatura de saturação indisponível para o refrigerante selecionado."
                continuation_requirement = "Disponibilizar propriedades termodinâmicas válidas do refrigerante para conversão P/T."
        inconclusive_location = thermal_deviation and first == "NÃO LOCALIZADO"
        diagnosis = ("DIAGNÓSTICO INCONCLUSIVO — CONVERSÃO TERMODINÂMICA INDISPONÍVEL" if inconclusive_location and not missing and thermodynamic_note else
                     "DIAGNÓSTICO INCONCLUSIVO — DADOS ADICIONAIS NECESSÁRIOS PARA LOCALIZAR A ORIGEM" if inconclusive_location else
                     "DIAGNÓSTICO INCONCLUSIVO" if missing else "COMPORTAMENTO FORA DA REFERÊNCIA" if first else "SEM DESVIO IDENTIFICADO")
        if missing:
            for key in ("evaporator", "suction_line"):
                if stages[key].status is ScanStatus.NOT_ANALYZED:
                    stages[key] = ScanStage(key, dict(STAGE_ORDER)[key], ScanStatus.INSUFFICIENT)
            hypothesis = "NÃO DETERMINADA"
            if not inconclusive_location:
                location = "Não foi possível diferenciar evaporador de linha de sucção"
                localization_reason = "Faltam medições entre evaporador e compressor."
                purpose = "Essas medições são necessárias para determinar se a queda de pressão/temperatura equivalente já ocorre no evaporador ou se aparece entre a saída do evaporador e a entrada do compressor."
            recommendations = tuple(f"Medir {name}" for name in missing)
        evidence = tuple(dict.fromkeys(e for m in measurements for e in m.evidence_ids))
        usable = sum(m.valid for m in measurements); analyzed = sum(s.status not in (ScanStatus.NOT_ANALYZED, ScanStatus.INSUFFICIENT) for s in stages.values())
        evaluated = analyzed + (1 if preliminary in (ScanStatus.NORMAL, ScanStatus.DEVIATION) else 0)
        confidence = None if not first or missing else min(.95, .35 + .05*usable + .06*analyzed)
        reason = f"Confiança não determinada: medições insuficientes; {evaluated} etapa(s) avaliada(s)." if confidence is None else f"{usable} medição(ões) válida(s), {evaluated} etapa(s) avaliada(s) e {len(evidence)} evidência(s)."
        return MachineScanResult(f"VTM-{uuid.uuid4().hex[:12].upper()}", session_id, execution_id, datetime.now().astimezone().isoformat(), reference, measurements, tuple(deviations), tuple(stages[k] for k, _ in STAGE_ORDER), first, location, diagnosis, hypothesis, evidence, tuple(dict.fromkeys(missing)), recommendations, confidence, reason, preliminary, evaluated, localization_reason, purpose, thermodynamic_note, thermodynamic_points, continuation_requirement, specialized_results or {})

    def _inconclusive(self, reference, measurements, session_id, execution_id, missing, specialized):
        stages = tuple(ScanStage(key, name, ScanStatus.INSUFFICIENT) for key, name in STAGE_ORDER)
        return MachineScanResult(f"VTM-{uuid.uuid4().hex[:12].upper()}", session_id, execution_id, datetime.now().astimezone().isoformat(), reference, measurements, (), stages, None, "NÃO DETERMINADA", "DIAGNÓSTICO INCONCLUSIVO", "NÃO DETERMINADA", tuple(e for m in measurements for e in m.evidence_ids), tuple(missing), tuple(f"Medir/cadastrar {m}" for m in missing), None, "Confiança não determinada: dados insuficientes; 0 etapa(s) avaliada(s).", ScanStatus.INSUFFICIENT, 0, "Condição térmica geral não avaliada.", "", "", (), "", specialized or {})

    @staticmethod
    def _measurement(indexed, canonical):
        return next((indexed[name] for name in ALIASES.get(canonical, (canonical,)) if name in indexed), None)

    @staticmethod
    def _number(value): return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

    @staticmethod
    def _stage(identifier, status, engineering=(), measurements=(), hypothesis="NÃO DETERMINADA", recommendations=()):
        return ScanStage(identifier, dict(STAGE_ORDER)[identifier], status, tuple(engineering), tuple(measurements), (), tuple(dict.fromkeys(e for m in measurements for e in m.evidence_ids)), hypothesis, tuple(recommendations))


class MachineScanRepository:
    """Histórico append-only de varreduras; nunca sobrescreve análises anteriores."""

    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._schema()

    def _connect(self):
        connection = sqlite3.connect(self.path); connection.row_factory = sqlite3.Row; return connection

    def _schema(self):
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS machine_scans(id TEXT PRIMARY KEY, session_id TEXT, execution_id TEXT, created_at TEXT NOT NULL, payload_json TEXT NOT NULL)")

    def save(self, result: MachineScanResult) -> None:
        payload = json.dumps(asdict(result), ensure_ascii=False, default=lambda value: value.value if isinstance(value, StrEnum) else str(value))
        with self._connect() as connection:
            connection.execute("INSERT INTO machine_scans VALUES(?,?,?,?,?)", (result.id, result.session_id, result.execution_id, result.created_at, payload))

    def list(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if session_id is None: rows = connection.execute("SELECT payload_json FROM machine_scans ORDER BY created_at DESC").fetchall()
            else: rows = connection.execute("SELECT payload_json FROM machine_scans WHERE session_id=? ORDER BY created_at DESC", (session_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]
