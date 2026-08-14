from types import SimpleNamespace

import pytest

from ipro_bench.coil_calculator import CoilGeometry, FinnedCoilCalculator
from ipro_bench.defrost_investigation import investigate_defrost
from ipro_bench.refrigeration_analysis import ReadingStatus, RefrigerationAnalyzer
from ipro_bench.time_utils import brasilia_text


def test_horario_e_apresentado_em_brasilia():
    assert brasilia_text("2026-08-14T15:00:00+00:00").startswith("14/08/2026 12:00:00")


def test_superaquecimento_subresfriamento_e_hipotese_sao_rastreaveis():
    analyzer = RefrigerationAnalyzer(lambda *_: (15.0, -5.0), lambda *_: (2.0, 40.0))
    superheat = analyzer.superheat(30, 10, "R404A")
    subcooling = analyzer.subcooling(200, 38, "R404A")
    result = analyzer.assess_charge(superheat, subcooling)
    assert superheat.status is ReadingStatus.ATTENTION
    assert subcooling.status is ReadingStatus.ATTENTION
    assert result.hypothesis.startswith("POSSÍVEL")
    assert result.alternatives and result.technician_checks
    assert result.confidence is not None


def test_dados_frigorificos_ausentes_nao_geram_conclusao():
    result = RefrigerationAnalyzer().superheat(None, 5, "R404A")
    assert result.status is ReadingStatus.INSUFFICIENT
    assert result.value_c is None


def test_calculo_da_serpentina_expoe_areas_e_formula():
    result = FinnedCoilCalculator.calculate(CoilGeometry(10, .01, 1, 100, .4, .5, .0001))
    assert result.total_exchange_area_m2 == pytest.approx(result.tube_external_area_m2 + result.effective_fin_area_m2)
    assert result.fpi == pytest.approx(2.54)
    assert len(result.formula) >= 5


def test_serpentina_rejeita_geometria_invalida():
    with pytest.raises(ValueError):
        FinnedCoilCalculator.calculate(CoilGeometry(0, .01, 1, 100, .4, .5, .0001))


def test_investigacao_de_degelo_usa_multiplas_familias_e_confianca_dinamica():
    cycle = SimpleNamespace(session_id="DIA-1", status=SimpleNamespace(value="COMPLETO"), quality_score=.9,
                            start_ns=1, end_ns=2, duration_seconds=120, evidence_ids=(1, 2), state_events=({},), alarms=())
    rows = (
        {"timestamp_ns": 1, "timestamp": "2026-08-14T12:00:00-03:00", "variable_id": "temperature_evaporator", "kind": "AMOSTRA"},
        {"timestamp_ns": 2, "timestamp": "2026-08-14T12:02:00-03:00", "variable_id": "current_compressor", "kind": "AMOSTRA"},
        {"timestamp_ns": 2, "timestamp": "2026-08-14T12:02:00-03:00", "variable_id": "pressure_suction", "kind": "AMOSTRA"},
    )
    result = investigate_defrost(cycle, rows)
    assert result.conclusion == "DEGELO NORMAL"
    assert set(result.families) == {"TEMPERATURE", "PRESSURE", "ELECTRICAL", "STATE"}
    assert result.confidence and result.confidence > .8
    assert result.evidence_ids == (1, 2)
