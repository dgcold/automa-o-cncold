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
    id: str = field(default_factory=lambda: f"TST-{uuid.uuid4().hex[:8].upper()}")
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())


class TestManager:
    __test__ = False
    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence
        self.tests: list[BenchTest] = []

    def create(self, test: BenchTest) -> BenchTest:
        self.tests.append(test)
        self.evidence.append("testes", {"event": "TEST_CREATED", "test": asdict(test)}, session=test.id)
        return test

    def finish(self, test_id: str, result: TestResult, observed: str) -> BenchTest:
        test = next((item for item in self.tests if item.id == test_id), None)
        if test is None:
            raise KeyError(test_id)
        test.result = result
        test.observed = observed
        self.evidence.append("testes", {"event": "TEST_FINISHED", "test": asdict(test)}, session=test.id)
        return test

    def summary(self) -> dict[str, int]:
        result = {item.value: 0 for item in TestResult}
        for test in self.tests:
            result[test.result.value] += 1
        result["TOTAL"] = len(self.tests)
        return result
