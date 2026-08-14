from ipro_bench.analysis_integration import SessionEvidenceInterpreter
from ipro_bench.anomaly_analysis import AnomalyClass, AnomalyEngine, AnomalyRepository
import pytest
from ipro_bench.baseline import BaselineRepository
from ipro_bench.explainable_diagnostics import (
    DiagnosticRepository, ExplainableDiagnosticEngine, deterministic_observation_rules,
)
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore
from ipro_bench.history_store import PersistentHistory
from ipro_bench.reports import ReportExporter
from ipro_bench.scenario_catalog import default_scenarios
from ipro_bench.scenario_executor import ScenarioExecutor


def services(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3")
    executor=ScenarioExecutor(PersistentHistory(tmp_path/"history.sqlite3"),BlackBoxRecorder(store),store,ReportExporter(tmp_path/"reports"))
    anomaly=AnomalyEngine(store,BaselineRepository(tmp_path/"baselines.sqlite3"),AnomalyRepository(tmp_path/"anomalies.sqlite3"))
    diagnostic=ExplainableDiagnosticEngine(store,DiagnosticRepository(tmp_path/"diagnostics.sqlite3"),deterministic_observation_rules())
    return store,executor,anomaly,diagnostic


def test_phase_imbalance_scenario_reaches_ai_and_explainable_diagnosis(tmp_path):
    store,executor,anomaly,diagnostic=services(tmp_path)
    result=executor.execute(default_scenarios()[9],seed=110,speed=100,step_seconds=5)

    assert result.samples==768
    assert store.resolve_session_id(result.execution_id)==result.session_id
    rows=store.query(result.session_id)
    assert len([row for row in rows if row["kind"]=="AMOSTRA"])==768

    facts=SessionEvidenceInterpreter(store).extract(result.execution_id)
    phase=next(item for item in facts if item.name=="phase_current_imbalance")
    assert len(phase.evidence_ids)==3
    assert all(any(row["id"]==identifier for row in rows) for identifier in phase.evidence_ids)

    ai=anomaly.analyze_recorded(result.execution_id)
    assert ai.session_id==result.session_id
    assert ai.classification is AnomalyClass.ANOMALOUS
    assert ai.evidence_ids==phase.evidence_ids and ai.factors

    hypotheses=diagnostic.evaluate_recorded(result.execution_id)
    assert len(hypotheses)==1
    assert hypotheses[0].description=="Possível desequilíbrio de corrente entre fases."
    assert hypotheses[0].evidence_ids==phase.evidence_ids
    assert hypotheses[0].causality=="NÃO ESTABELECIDA"


def test_normal_scenario_does_not_force_phase_hypothesis(tmp_path):
    _,executor,anomaly,diagnostic=services(tmp_path)
    result=executor.execute(default_scenarios()[1],seed=102,speed=100,step_seconds=5)
    assert diagnostic.evaluate_recorded(result.execution_id)==[]
    ai=anomaly.analyze_recorded(result.execution_id)
    assert ai.classification is AnomalyClass.NORMAL
    assert ai.abstention_reason is None


@pytest.mark.parametrize("index,expected",[
    (0,"compressor_command_without_feedback"),(1,None),(2,"compressor_command_without_feedback"),
    (3,"condenser_fan_without_feedback"),(4,"invalid_sensor_reading"),(5,"communication_loss_observed"),
    (6,"incomplete_defrost_cycle"),(7,"slow_thermal_recovery"),(8,"high_compressor_current"),(9,"phase_current_imbalance"),
])
def test_all_scenarios_reach_evidence_ai_and_diagnosis(index,expected,tmp_path):
    store,executor,anomaly,diagnostic=services(tmp_path);result=executor.execute(default_scenarios()[index],seed=300+index,speed=100,step_seconds=5)
    interpretation=SessionEvidenceInterpreter(store).interpret(result.execution_id)
    assert result.session_id==interpretation.session_id and result.samples==interpretation.sample_count
    names={fact.name for fact in interpretation.facts}
    if expected is None:
        assert interpretation.state=="SEM ANOMALIA" and not names
    else:
        assert expected in names and interpretation.state=="ANOMALIA DETECTADA"
    ai=anomaly.analyze_recorded(result.execution_id);hypotheses=diagnostic.evaluate_recorded(result.execution_id)
    assert ai.session_id==result.session_id and ai.state.value=="CONCLUÍDA"
    assert ai.classification is (AnomalyClass.NORMAL if expected is None else AnomalyClass.ANOMALOUS)
    assert (not hypotheses) if expected is None else bool(hypotheses)
    assert all(item.causality=="NÃO ESTABELECIDA" for item in hypotheses)


def test_missing_and_empty_sessions_are_distinct(tmp_path):
    store,_,anomaly,diagnostic=services(tmp_path);empty=BlackBoxRecorder(store);session=empty.start("simulator","vazia");empty.stop()
    assert SessionEvidenceInterpreter(store).interpret(session.id).state=="SEM DADOS"
    assert anomaly.analyze_recorded(session.id).abstention_reason=="SEM DADOS"
    assert diagnostic.evaluate_recorded(session.id)==[]
    with pytest.raises(KeyError):SessionEvidenceInterpreter(store).interpret("DIA-INEXISTENTE")
