import json

import pytest

from ipro_bench.core import BenchState, OperationMode
from ipro_bench.evidence import EVIDENCE_CATEGORIES, EvidenceStore
from ipro_bench.mapping import ModbusMapRepository
from ipro_bench.test_manager import BenchTest, TestManager, TestResult


def test_real_mode_is_read_only():
    state = BenchState()
    state.set_mode(OperationMode.REAL_READ_ONLY)
    assert state.read_only is True


def test_simulator_mode_is_not_real_read_only():
    assert BenchState().read_only is False


def test_evidence_creates_all_categories(tmp_path):
    EvidenceStore(tmp_path)
    assert all((tmp_path / name).is_dir() for name in EVIDENCE_CATEGORIES)


def test_evidence_is_append_only_jsonl(tmp_path):
    store = EvidenceStore(tmp_path)
    path = store.append("tcp", {"event": "A"})
    store.append("tcp", {"event": "B"})
    assert [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines()] == ["A", "B"]


def test_evidence_rejects_unknown_category(tmp_path):
    with pytest.raises(ValueError):
        EvidenceStore(tmp_path).append("other", {})


def test_initial_map_is_valid(project_dir):
    repo = ModbusMapRepository(project_dir / "config" / "modbus_map.json", project_dir / "history")
    result = repo.validate_payload(repo.load())
    assert result.valid
    assert result.variable_count == 9


def test_map_rejects_write_function(project_dir):
    repo = ModbusMapRepository(project_dir / "config" / "modbus_map.json", project_dir / "history")
    payload = repo.load()
    payload["variables"][0]["function"] = 6
    result = repo.validate_payload(payload)
    assert not result.valid
    assert "FC03/FC04" in " ".join(result.errors)


def test_initial_map_has_no_active_addresses(project_dir):
    repo = ModbusMapRepository(project_dir / "config" / "modbus_map.json", project_dir / "history")
    assert all(item["address"] is None for item in repo.load()["variables"])


def test_test_manager_records_lifecycle(tmp_path):
    store = EvidenceStore(tmp_path)
    manager = TestManager(store)
    test = manager.create(BenchTest("Sensor", "Validar sensor", "SENSOR"))
    manager.finish(test.id, TestResult.APPROVED, "Valor acompanhado")
    assert manager.summary()["APROVADO"] == 1
    assert store.count("testes") == 2


@pytest.fixture
def project_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
