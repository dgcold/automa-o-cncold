from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

from .evidence import EvidenceStore


class ScenarioStatus(StrEnum):
    DRAFT = "RASCUNHO"
    READY = "PRONTO"
    RUNNING = "EM EXECUÇÃO"
    COMPLETED = "CONCLUÍDO"
    CANCELLED = "CANCELADO"


class ScenarioAction(StrEnum):
    SET_STATE = "DEFINIR_ESTADO"
    COMMAND_COMPRESSOR = "COMANDAR_COMPRESSOR"
    INJECT_FAULT = "INJETAR_FALHA"
    CLEAR_FAULT = "REMOVER_FALHA"
    STOP = "FINALIZAR"


class CriterionOutcome(StrEnum):
    PASSED = "PASSOU"
    FAILED = "FALHOU"
    UNDETERMINED = "NÃO DETERMINADO"


@dataclass(frozen=True)
class ScenarioStep:
    at_seconds: float
    action: ScenarioAction
    target: str = "machine"
    parameters: dict = field(default_factory=dict)
    condition: str = ""
    duration_seconds: float | None = None
    expectation: str = ""
    fault: str | None = None


@dataclass(frozen=True)
class TestCriterion:
    __test__ = False
    name: str
    event: str
    should_exist: bool = True
    maximum_seconds: float | None = None
    evidence_family: str = ""


@dataclass
class Scenario:
    name: str
    description: str
    steps: list[str | ScenarioStep] = field(default_factory=list)
    criteria: list[TestCriterion] = field(default_factory=list)
    duration_seconds: float = 60.0
    safe_offline: bool = True
    id: str = field(default_factory=lambda: f"CEN-{uuid.uuid4().hex[:8].upper()}")
    status: ScenarioStatus = ScenarioStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())


class ScenarioManager:
    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence
        self.scenarios: list[Scenario] = []

    def create(self, scenario: Scenario) -> Scenario:
        self.scenarios.append(scenario)
        self.evidence.append("cenarios", {"event": "SCENARIO_CREATED", "scenario": asdict(scenario)}, scenario.id)
        return scenario

    def mark_ready(self, scenario_id: str) -> Scenario:
        return self._transition(scenario_id, ScenarioStatus.READY)

    def start_offline(self, scenario_id: str) -> Scenario:
        scenario = self.get(scenario_id)
        if not scenario.safe_offline:
            raise PermissionError("Cenário físico bloqueado nesta etapa.")
        if scenario.status is not ScenarioStatus.READY:
            raise ValueError("O cenário precisa estar PRONTO.")
        return self._transition(scenario_id, ScenarioStatus.RUNNING)

    def finish(self, scenario_id: str) -> Scenario:
        return self._transition(scenario_id, ScenarioStatus.COMPLETED)

    def get(self, scenario_id: str) -> Scenario:
        scenario = next((item for item in self.scenarios if item.id == scenario_id), None)
        if scenario is None:
            raise KeyError(scenario_id)
        return scenario

    def _transition(self, scenario_id: str, status: ScenarioStatus) -> Scenario:
        scenario = self.get(scenario_id)
        scenario.status = status
        self.evidence.append("cenarios", {"event": "SCENARIO_STATUS", "status": status.value}, scenario.id)
        return scenario
