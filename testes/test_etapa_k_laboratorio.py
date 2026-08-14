import pytest

from ipro_bench.evidence import EvidenceStore
from ipro_bench.field_diagnostics import (
    BlackBoxRecorder,
    BlackBoxStore,
    TimelineAnalyzer,
)
from ipro_bench.history_store import PersistentHistory
from ipro_bench.reports import ReportExporter
from ipro_bench.scenario_catalog import default_scenarios
from ipro_bench.scenario_executor import ExecutionStatus, ScenarioExecutor, SimulatedMachineCondition
from ipro_bench.scenarios import (
    CriterionOutcome,
    Scenario,
    ScenarioAction,
    ScenarioStep,
    TestCriterion,
)
from ipro_bench.test_manager import BenchTest, TestManager
from ipro_bench.virtual_machine import MachineState, VirtualRefrigerationMachine


def scenario_failure():
    return Scenario("TESTE 01 - FALHA DE RECUPERACAO POS-DEGELO", "Offline", steps=[
        ScenarioStep(0, ScenarioAction.SET_STATE, parameters={"state": MachineState.STOPPED.value}),
        ScenarioStep(10, ScenarioAction.SET_STATE, parameters={"state": MachineState.STARTING.value}),
        ScenarioStep(20, ScenarioAction.SET_STATE, parameters={"state": MachineState.COOLING.value}),
        ScenarioStep(120, ScenarioAction.SET_STATE, parameters={"state": MachineState.STABLE.value}),
        ScenarioStep(300, ScenarioAction.SET_STATE, parameters={"state": MachineState.DEFROST.value}),
        ScenarioStep(360, ScenarioAction.SET_STATE, parameters={"state": MachineState.DRIPPING.value}),
        ScenarioStep(390, ScenarioAction.SET_STATE, parameters={"state": MachineState.RETURNING.value}),
        ScenarioStep(400, ScenarioAction.SET_STATE, parameters={"state": MachineState.RECOVERY.value}),
        ScenarioStep(410, ScenarioAction.COMMAND_COMPRESSOR, parameters={"enabled": True}),
        ScenarioStep(411, ScenarioAction.INJECT_FAULT, fault="COMPRESSOR_NAO_RETORNA_POS_DEGELO"),
    ], criteria=[
        TestCriterion("Desvio deve existir", "COMPRESSOR_COMANDADO_SEM_RESPOSTA", True),
        TestCriterion("Recuperação deve existir", "RECUPERACAO", True),
    ], duration_seconds=700)


def test_machine_is_deterministic():
    a, b = VirtualRefrigerationMachine(42), VirtualRefrigerationMachine(42)
    a.transition(MachineState.COOLING); b.transition(MachineState.COOLING)
    for _ in range(10): a.tick(1); b.tick(1)
    assert a.chamber_temperature == b.chamber_temperature


def test_integrated_end_to_end(tmp_path):
    store = BlackBoxStore(tmp_path / "blackbox.sqlite3")
    history = PersistentHistory(tmp_path / "history.sqlite3")
    result = ScenarioExecutor(history, BlackBoxRecorder(store), store, ReportExporter(tmp_path / "reports")).execute(
        scenario_failure(), seed=123, speed=100, step_seconds=5)
    assert result.samples >= 1000
    assert result.scenario_id and result.execution_id and result.session_id
    assert result.technical_result is CriterionOutcome.FAILED
    assert TimelineAnalyzer(store).first_deviation(result.session_id)
    assert history.count() == result.samples
    assert all(path.exists() for path in result.report_paths.values())
    assert {item["event"] for item in result.events} >= {"DEGELO_INICIO", "DEGELO_FIM", "GOTEJAMENTO_FIM", "RETORNO_REFRIGERACAO", "COMPRESSOR_COMANDADO_SEM_RESPOSTA"}
    manager = TestManager(EvidenceStore(tmp_path / "evidence"))
    test = manager.create(BenchTest("E2E", "Execução integrada", "SIMULADOR", scenario_id=result.scenario_id))
    manager.start(test.id)
    linked = manager.attach_execution(test.id, result)
    assert (linked.scenario_id, linked.execution_id, linked.session_id) == (result.scenario_id, result.execution_id, result.session_id)
    assert TimelineAnalyzer(store).first_deviation(result.session_id)["id"] > 0
    assert manager.evidence.count("testes") == 3


def test_test_01_reproduces_expected_fault_and_passes(tmp_path):
    scenario = default_scenarios()[0]
    fault_step = next(step for step in scenario.steps if isinstance(step, ScenarioStep) and step.fault == "COMPRESSOR_NAO_RETORNA_POS_DEGELO")
    command_step = next(step for step in scenario.steps if isinstance(step, ScenarioStep) and step.action is ScenarioAction.COMMAND_COMPRESSOR)
    assert fault_step.at_seconds < command_step.at_seconds
    assert [(criterion.event, criterion.should_exist) for criterion in scenario.criteria] == [
        ("COMPRESSOR_COMANDADO_SEM_RESPOSTA", True),
    ]

    store = BlackBoxStore(tmp_path / "blackbox.sqlite3")
    result = ScenarioExecutor(PersistentHistory(tmp_path / "history.sqlite3"), BlackBoxRecorder(store),
                              store, ReportExporter(tmp_path / "reports")).execute(
        scenario, seed=123, speed=100, step_seconds=5)

    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.scenario_verdict is CriterionOutcome.PASSED
    assert result.simulated_condition is SimulatedMachineCondition.SIMULATED_FAULT
    assert result.simulated_condition_detail == "FALHA DE RECUPERAÇÃO PÓS-DEGELO"
    assert result.diagnosis is SimulatedMachineCondition.ANOMALY_DETECTED
    assert "COMPRESSOR_COMANDADO_SEM_RESPOSTA" in {item["event"] for item in result.events}
    assert "RECUPERACAO" not in {item["event"] for item in result.events}


def test_unmet_criterion_still_fails(tmp_path):
    scenario = Scenario("Critério não atendido", "Offline",
                        criteria=[TestCriterion("Evento obrigatório", "EVENTO_INEXISTENTE", True)],
                        duration_seconds=1)
    store = BlackBoxStore(tmp_path / "blackbox.sqlite3")
    result = ScenarioExecutor(PersistentHistory(tmp_path / "history.sqlite3"), BlackBoxRecorder(store),
                              store, ReportExporter(tmp_path / "reports")).execute(
        scenario, speed=100, step_seconds=1)
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.scenario_verdict is CriterionOutcome.FAILED


def test_execution_exception_remains_an_execution_error(monkeypatch, tmp_path):
    store = BlackBoxStore(tmp_path / "blackbox.sqlite3")
    executor = ScenarioExecutor(PersistentHistory(tmp_path / "history.sqlite3"),
                                BlackBoxRecorder(store), store, ReportExporter(tmp_path / "reports"))
    monkeypatch.setattr("ipro_bench.scenario_executor.SimulationEngine.run_headless",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("falha real")))
    with pytest.raises(RuntimeError, match="falha real"):
        executor.execute(default_scenarios()[0], speed=100)


@pytest.mark.parametrize("index", range(10))
def test_all_professional_scenarios_execute(index, tmp_path):
    store = BlackBoxStore(tmp_path / "blackbox.sqlite3")
    result = ScenarioExecutor(PersistentHistory(tmp_path / "history.sqlite3"), BlackBoxRecorder(store),
                              store, ReportExporter(tmp_path / "reports")).execute(
        default_scenarios()[index], seed=100 + index, speed=100, step_seconds=20)
    assert result.samples >= 190
    assert result.status.value == "FINALIZADO"
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.technical_result in (CriterionOutcome.PASSED, CriterionOutcome.FAILED)
