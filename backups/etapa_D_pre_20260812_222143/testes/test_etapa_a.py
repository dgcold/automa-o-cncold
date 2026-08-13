import json

import pytest

from ipro_bench.core import DataQuality
from ipro_bench.electrical import ElectricalMeasurementService
from ipro_bench.evidence import EvidenceStore
from ipro_bench.history_store import PersistentHistory
from ipro_bench.reports import ReportExporter
from ipro_bench.scenarios import Scenario, ScenarioManager, ScenarioStatus
from ipro_bench.telemetry import TelemetrySample
from ipro_bench.test_manager import BenchTest, TestManager, TestResult, TestStatus


def test_disconnected_telemetry_never_invents_value():
    with pytest.raises(ValueError):
        TelemetrySample("x", "X", "SENSOR", "°C", 12.0, DataQuality.VALID, connected=False)


def test_no_data_never_contains_value():
    with pytest.raises(ValueError):
        TelemetrySample("x", "X", "SENSOR", "°C", 12.0, DataQuality.NO_DATA, connected=True)


def test_electrical_starts_disconnected_and_empty():
    snapshot = ElectricalMeasurementService().snapshot()
    assert snapshot.connected is False
    assert len(snapshot.samples) == 5
    assert all(sample.value is None and sample.display_value == "SEM DADOS" for sample in snapshot.samples)


def test_electrical_ingest_records_values_and_missing_channels(tmp_path):
    history = PersistentHistory(tmp_path / "history.sqlite3")
    service = ElectricalMeasurementService(history)
    snapshot = service.ingest({"current_total": 10.0, "current_l1": 0.0})
    assert snapshot.connected is True
    assert snapshot.samples[0].value == 10.0
    assert snapshot.samples[2].value == 0.0
    assert snapshot.samples[1].quality is DataQuality.NO_DATA
    assert history.count() == 5


def test_history_statistics_include_zero(tmp_path):
    history = PersistentHistory(tmp_path / "history.sqlite3")
    for value in (0.0, 5.0, 10.0):
        history.append(TelemetrySample("l1", "L1", "ELÉTRICA", "A", value, DataQuality.VALID, "TESTE", True))
    assert history.statistics("l1") == {"count": 3, "average": 5.0, "minimum": 0.0, "maximum": 10.0}


def test_history_query_is_chronological(tmp_path):
    history = PersistentHistory(tmp_path / "history.sqlite3")
    history.append(TelemetrySample("x", "X", "S", "u", 1, DataQuality.VALID, "T", True))
    history.append(TelemetrySample("x", "X", "S", "u", 2, DataQuality.VALID, "T", True))
    assert [row["value"] for row in history.query("x")] == [1.0, 2.0]


def test_physical_scenario_is_blocked(tmp_path):
    manager = ScenarioManager(EvidenceStore(tmp_path))
    scenario = manager.create(Scenario("Físico", "Não executar", safe_offline=False))
    manager.mark_ready(scenario.id)
    with pytest.raises(PermissionError):
        manager.start_offline(scenario.id)


def test_offline_scenario_lifecycle(tmp_path):
    manager = ScenarioManager(EvidenceStore(tmp_path))
    scenario = manager.create(Scenario("Offline", "Seguro"))
    manager.mark_ready(scenario.id)
    assert manager.start_offline(scenario.id).status is ScenarioStatus.RUNNING
    assert manager.finish(scenario.id).status is ScenarioStatus.COMPLETED


def test_complete_test_manager_lifecycle(tmp_path):
    manager = TestManager(EvidenceStore(tmp_path))
    test = manager.create(BenchTest("Teste", "Objetivo", "OFFLINE"))
    assert manager.prepare(test.id).status is TestStatus.READY
    assert manager.start(test.id).status is TestStatus.RUNNING
    finished = manager.finish(test.id, TestResult.APPROVED, "OK")
    assert finished.status is TestStatus.FINISHED
    assert finished.finished_at


def test_reports_export_json_csv_pdf(tmp_path):
    exporter = ReportExporter(tmp_path)
    rows = [{"canal": "L1", "valor": None, "status": "SEM DADOS"}]
    json_path = exporter.json(rows)
    csv_path = exporter.csv(rows)
    pdf_path = exporter.pdf("Relatório", rows)
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["valor"] is None
    assert "SEM DADOS" in csv_path.read_text(encoding="utf-8-sig")
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")


def test_electrical_disconnect_clears_previous_values():
    service = ElectricalMeasurementService()
    service.ingest({"current_total": 12})
    snapshot = service.disconnect()
    assert not snapshot.connected
    assert all(sample.value is None for sample in snapshot.samples)
