from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

from .evidence import EvidenceStore


class TestResult(StrEnum):
    __test__ = False
    NOT_VALIDATED = "NÃO VALIDADO"
    APPROVED = "APROVADO"
    FAILED = "REPROVADO"
    NOT_CONFIRMED = "NÃO CONFIRMADO"
    CANCELLED = "CANCELADO"


class TestStatus(StrEnum):
    __test__ = False
    DRAFT = "RASCUNHO"
    READY = "PRONTO"
    RUNNING = "EM EXECUÇÃO"
    FINISHED = "FINALIZADO"
    CANCELLED = "CANCELADO"


@dataclass
class BenchTest:
    name: str
    objective: str
    category: str
    operator: str = ""
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    observed: str = ""
    result: TestResult = TestResult.NOT_VALIDATED
    status: TestStatus = TestStatus.DRAFT
    notes: str = ""
    id: str = field(default_factory=lambda: f"TST-{uuid.uuid4().hex[:8].upper()}")
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    scenario_id: str | None = None
    execution_id: str | None = None
    session_id: str | None = None
    technical_result: str = "NÃO DETERMINADO"
    criteria: list[dict] = field(default_factory=list)


class TestManager:
    __test__ = False
    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence
        self.tests: list[BenchTest] = []

    def create(self, test: BenchTest) -> BenchTest:
        self.tests.append(test)
        self.evidence.append("testes", {"event": "TEST_CREATED", "test": asdict(test)}, session=test.id)
        return test

    def get(self, test_id: str) -> BenchTest:
        test = next((item for item in self.tests if item.id == test_id), None)
        if test is None:
            raise KeyError(test_id)
        return test

    def prepare(self, test_id: str) -> BenchTest:
        test = self.get(test_id)
        test.status = TestStatus.READY
        self._record("TEST_READY", test)
        return test

    def start(self, test_id: str) -> BenchTest:
        test = self.get(test_id)
        if test.status not in (TestStatus.DRAFT, TestStatus.READY):
            raise ValueError("Teste não está disponível para início.")
        test.status = TestStatus.RUNNING
        test.started_at = datetime.now().astimezone().isoformat()
        self._record("TEST_STARTED", test)
        return test

    def finish(self, test_id: str, result: TestResult, observed: str) -> BenchTest:
        test = self.get(test_id)
        test.result = result
        test.observed = observed
        test.status = TestStatus.FINISHED
        test.finished_at = datetime.now().astimezone().isoformat()
        self._record("TEST_FINISHED", test)
        return test

    def attach_execution(self, test_id: str, execution) -> BenchTest:
        test = self.get(test_id)
        test.scenario_id = execution.scenario_id
        test.execution_id = execution.execution_id
        test.session_id = execution.session_id
        test.technical_result = execution.technical_result.value
        test.criteria = [asdict(item) for item in execution.criteria]
        self._record("TECHNICAL_EXECUTION_ATTACHED", test)
        return test

    def cancel(self, test_id: str, reason: str = "") -> BenchTest:
        test = self.get(test_id)
        test.status = TestStatus.CANCELLED
        test.result = TestResult.CANCELLED
        test.notes = reason
        test.finished_at = datetime.now().astimezone().isoformat()
        self._record("TEST_CANCELLED", test)
        return test

    def _record(self, event: str, test: BenchTest) -> None:
        self.evidence.append("testes", {"event": event, "test": asdict(test)}, session=test.id)

    def summary(self) -> dict[str, int]:
        result = {item.value: 0 for item in TestResult}
        for test in self.tests:
            result[test.result.value] += 1
        result["TOTAL"] = len(self.tests)
        return result
