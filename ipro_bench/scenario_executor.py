from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from .core import DataQuality
from .defrost_analysis import DefrostCycleAnalyzer
from .event_engine import EventEngine
from .fault_injection import FaultInjector
from .field_diagnostics import BlackBoxRecorder, BlackBoxStore, TimelineAnalyzer
from .history_store import PersistentHistory
from .incident_analysis import IncidentAnalyzer
from .reports import ReportExporter
from .scenarios import (
    CriterionOutcome,
    Scenario,
    ScenarioAction,
    ScenarioStep,
    TestCriterion,
)
from .simulation_engine import SimulationEngine, SimulationStatus
from .telemetry import TelemetrySample
from .telemetry_bus import TelemetryBus
from .virtual_electrical import VirtualElectricalInstrumentation
from .virtual_machine import MachineState, VirtualRefrigerationMachine
from .analysis_integration import SessionEvidenceInterpreter


@dataclass(frozen=True)
class CriterionResult:
    criterion: str
    outcome: CriterionOutcome
    detail: str


class ExecutionStatus(StrEnum):
    COMPLETED = "CONCLUÍDA"
    EXECUTION_ERROR = "ERRO DE EXECUÇÃO"
    CANCELLED = "CANCELADO"


class SimulatedMachineCondition(StrEnum):
    NORMAL = "NORMAL"
    ANOMALY_DETECTED = "ANOMALIA DETECTADA"
    SIMULATED_FAULT = "FALHA SIMULADA"


@dataclass
class ExecutionResult:
    scenario_id: str
    execution_id: str
    session_id: str
    seed: int
    duration_seconds: float
    speed: int
    status: SimulationStatus
    samples: int
    faults: tuple[dict, ...]
    events: tuple[dict, ...]
    criteria: tuple[CriterionResult, ...]
    technical_result: CriterionOutcome
    report_paths: dict[str, Path] = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)

    @property
    def execution_status(self) -> ExecutionStatus:
        if self.status is SimulationStatus.FINISHED:
            return ExecutionStatus.COMPLETED
        return ExecutionStatus.CANCELLED

    @property
    def scenario_verdict(self) -> CriterionOutcome:
        return self.technical_result

    @property
    def simulated_condition(self) -> SimulatedMachineCondition:
        return SimulatedMachineCondition.SIMULATED_FAULT if self.faults else SimulatedMachineCondition.NORMAL

    @property
    def simulated_condition_detail(self) -> str:
        names = {item.get("name") for item in self.faults}
        if "COMPRESSOR_NAO_RETORNA_POS_DEGELO" in names:
            return "FALHA DE RECUPERAÇÃO PÓS-DEGELO"
        return self.simulated_condition.value

    @property
    def diagnosis(self) -> SimulatedMachineCondition:
        return SimulatedMachineCondition.ANOMALY_DETECTED if self.faults else SimulatedMachineCondition.NORMAL


class ScenarioExecutor:
    """Headless orchestrator. It has no real transport dependency."""

    def __init__(self, history: PersistentHistory, blackbox: BlackBoxRecorder,
                 blackbox_store: BlackBoxStore, reports: ReportExporter) -> None:
        self.history, self.blackbox, self.store, self.reports = history, blackbox, blackbox_store, reports
        self.current: ExecutionResult | None = None

    def execute(self, scenario: Scenario, *, seed: int = 1, speed: int = 100,
                step_seconds: float = 1.0) -> ExecutionResult:
        engine = SimulationEngine(seed=seed, speed=speed)
        machine = VirtualRefrigerationMachine(seed=seed)
        electrical = VirtualElectricalInstrumentation(seed=seed)
        injector = FaultInjector(machine)
        session = self.blackbox.start("simulator", scenario.name,
            f"scenario_id={scenario.id}; execution_id={engine.execution_id}; source=SIMULADOR")
        bus = TelemetryBus(self.history, self.blackbox)
        events = EventEngine(self.blackbox)
        structured = sorted((step for step in scenario.steps if isinstance(step, ScenarioStep)), key=lambda item: item.at_seconds)
        pending = list(structured)

        def tick(dt: float, timestamp: str) -> None:
            while pending and pending[0].at_seconds <= engine.elapsed:
                self._apply(pending.pop(0), machine, injector, events, timestamp, engine)
            machine.tick(dt)
            metadata = {"controller": "VIRTUAL_REFRIGERATION_MACHINE", "scenario_id": scenario.id,
                        "execution_id": engine.execution_id, "session_id": session.id, "seed": seed,
                        "machine_state": machine.state.value}
            samples = self._machine_samples(machine, timestamp, metadata) + electrical.samples(machine, timestamp, metadata)
            bus.publish(samples)
            events.observe(machine, timestamp, engine.elapsed)

        engine.run_headless(scenario.duration_seconds, tick, step_seconds)
        stopped = self.blackbox.stop()
        interpreted = SessionEvidenceInterpreter(self.store).interpret(session.id)
        criteria = tuple(self._criterion(item, events.events, interpreted.facts) for item in scenario.criteria)
        technical = self._technical(criteria)
        summary = TimelineAnalyzer(self.store).summary(session.id)
        cycles = DefrostCycleAnalyzer(self.store).identify(session.id)
        first = TimelineAnalyzer(self.store).first_deviation(session.id)
        investigation = None
        if first:
            investigation = IncidentAnalyzer(self.store).investigate(session.id, first["id"])
        result = ExecutionResult(scenario.id, engine.execution_id, stopped.id, seed, engine.elapsed, speed,
            engine.status, bus.published, tuple(asdict(item) for item in injector.injected), tuple(events.events),
            criteria, technical, analysis={"timeline": summary, "defrost": [asdict(item) for item in cycles],
                                           "incident": asdict(investigation) if investigation else "NÃO DETERMINADO",
                                           "baseline": "NÃO DETERMINADO", "diagnosis": interpreted.state,
                                           "anomaly": interpreted.state, "health": "DADOS INSUFICIENTES",
                                           "evidence_families": [asdict(item) for item in interpreted.facts],
                                           "data_quality": interpreted.quality})
        result.report_paths = self._reports(scenario, result)
        self.current = result
        return result

    @staticmethod
    def _apply(step: ScenarioStep, machine: VirtualRefrigerationMachine, injector: FaultInjector,
               events: EventEngine, timestamp: str, engine: SimulationEngine) -> None:
        if step.action is ScenarioAction.SET_STATE:
            machine.transition(MachineState(step.parameters.get("state", step.target)))
        elif step.action is ScenarioAction.COMMAND_COMPRESSOR:
            machine.command_compressor(bool(step.parameters.get("enabled", True)))
            events.command_event("COMANDO_COMPRESSOR", timestamp)
        elif step.action is ScenarioAction.INJECT_FAULT:
            injector.inject(step.fault or step.target, timestamp)
            events.command_event(f"FALHA_INJETADA:{step.fault or step.target}", timestamp)
        elif step.action is ScenarioAction.CLEAR_FAULT:
            injector.clear(step.fault or step.target)
        elif step.action is ScenarioAction.STOP:
            engine.stop()

    @staticmethod
    def _machine_samples(machine: VirtualRefrigerationMachine, timestamp: str, metadata: dict) -> tuple[TelemetrySample, ...]:
        channels = (
            ("temperature_chamber", "Temperatura da câmara", "SENSORES", "°C", machine.sensor_value("temperature_chamber")),
            ("temperature_evaporator", "Temperatura do evaporador", "SENSORES", "°C", machine.sensor_value("temperature_evaporator")),
            ("pressure_suction", "Pressão de sucção", "SENSORES", "psi", machine.sensor_value("pressure_suction")),
            ("pressure_discharge", "Pressão de descarga", "SENSORES", "psi", machine.sensor_value("pressure_discharge")),
            ("compressor_command", "Comando do compressor", "I/O", "bool", machine.compressor_command),
            ("compressor", "Estado do compressor", "I/O", "bool", machine.compressor),
            ("evaporator_fan", "Ventilador evaporador", "I/O", "bool", machine.evaporator_fan),
            ("condenser_fan", "Ventilador condensador", "I/O", "bool", machine.condenser_fan),
            ("defrost", "Degelo", "I/O", "bool", machine.defrost),
            ("dripping", "Gotejamento", "I/O", "bool", machine.dripping),
            ("communication", "Comunicação simulada", "COMUNICAÇÃO", "bool", machine.communication),
        )
        output = []
        invalid_sensor = bool(machine.faults & {"SENSOR_INVALIDO", "SENSOR_ABERTO", "SENSOR_CURTO"})
        for channel_id, name, group, unit, value in channels:
            quality = DataQuality.INVALID if channel_id == "temperature_chamber" and invalid_sensor else DataQuality.VALID
            output.append(TelemetrySample(channel_id, name, group, unit, value, quality, "SIMULADOR", True,
                                          timestamp, {**metadata, "machine_state": machine.state.value}))
        return tuple(output)

    @staticmethod
    def _criterion(criterion: TestCriterion, events: list[dict], evidence_facts=()) -> CriterionResult:
        if criterion.evidence_family:
            matches = list(evidence_facts) if criterion.evidence_family == "*" else [
                item for item in evidence_facts if item.name == criterion.evidence_family
            ]
            source = f"evidência {criterion.evidence_family}"
        else:
            matches = [item for item in events if item["event"] == criterion.event]
            source = f"evento {criterion.event}"
        passed = bool(matches) is criterion.should_exist
        return CriterionResult(criterion.name, CriterionOutcome.PASSED if passed else CriterionOutcome.FAILED,
            f"{source}: {len(matches)} ocorrência(s)")

    @staticmethod
    def _technical(criteria: tuple[CriterionResult, ...]) -> CriterionOutcome:
        if not criteria:
            return CriterionOutcome.UNDETERMINED
        return CriterionOutcome.FAILED if any(item.outcome is CriterionOutcome.FAILED for item in criteria) else CriterionOutcome.PASSED

    def _reports(self, scenario: Scenario, result: ExecutionResult) -> dict[str, Path]:
        row = {"scenario": scenario.name, "scenario_id": result.scenario_id, "execution_id": result.execution_id,
               "session_id": result.session_id, "seed": result.seed, "duration": result.duration_seconds,
               "speed": result.speed, "samples": result.samples, "faults": list(result.faults),
               "events": list(result.events), "first_deviation": result.analysis["timeline"].get("first_deviation"),
               "criteria": [asdict(item) for item in result.criteria], "technical_result": result.technical_result.value,
               "execution_status": result.execution_status.value, "scenario_verdict": result.scenario_verdict.value,
               "simulated_condition": result.simulated_condition.value,
               "simulated_condition_detail": result.simulated_condition_detail,
               "diagnosis": result.analysis["diagnosis"], "anomaly": result.analysis["anomaly"],
               "evidence_families": result.analysis["evidence_families"], "health": "NÃO DETERMINADO"}
        stem = f"execucao_{result.execution_id.lower()}"
        return {"json": self.reports.json([row], stem), "csv": self.reports.csv([row], stem),
                "pdf": self.reports.pdf("Relatório de Execução Simulada", [row], stem)}
