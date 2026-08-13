import json
import zipfile

import pytest

from ipro_bench.core import DataQuality
from ipro_bench.field_diagnostics import (
    BlackBoxRecorder, BlackBoxStore, SessionStatus, TimelineAnalyzer, TimelineKind,
    high_resolution_timestamp,
)
from ipro_bench.session_export import DiagnosticSessionExporter
from ipro_bench.telemetry import TelemetrySample


def sample(channel, value, timestamp, quality=DataQuality.VALID):
    return TelemetrySample(channel, channel, "PROCESSO", "u", value, quality, "OFFLINE", True, timestamp)


def test_high_resolution_clock_has_nanoseconds_and_timezone():
    timestamp, timestamp_ns = high_resolution_timestamp()
    assert timestamp_ns > 1_000_000_000_000_000_000
    assert "." in timestamp and (timestamp.endswith("+00:00") or "+" in timestamp[-6:] or "-" in timestamp[-6:])


def test_session_lifecycle_is_persistent(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    started = recorder.start("ipro", "Campo offline")
    assert store.get_session(started.id).status is SessionStatus.ACTIVE
    stopped = recorder.stop()
    assert stopped.status is SessionStatus.FINISHED
    assert stopped.ended_ns >= stopped.started_ns


def test_cannot_record_without_active_session(tmp_path):
    recorder = BlackBoxRecorder(BlackBoxStore(tmp_path / "box.sqlite3"))
    with pytest.raises(RuntimeError):
        recorder.ingest([])


def test_samples_and_state_changes_are_recorded(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.ingest([sample("compressor", False, "2026-01-01T00:00:00.000001+00:00")])
    recorder.ingest([sample("compressor", True, "2026-01-01T00:00:01.000001+00:00")])
    rows = store.query(session.id)
    assert [row["kind"] for row in rows] == ["AMOSTRA", "AMOSTRA", "MUDANÇA DE ESTADO"]
    assert rows[-1]["previous_value"] is False and rows[-1]["value"] is True


def test_quality_change_is_explicit(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.ingest([sample("sensor", 1, "2026-01-01T00:00:00+00:00")])
    recorder.ingest([sample("sensor", None, "2026-01-01T00:00:01+00:00", DataQuality.NO_DATA)])
    assert any(row["kind"] == TimelineKind.QUALITY_CHANGE.value for row in store.query(session.id))


def test_communication_loss_and_restore_are_not_duplicated(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("vx", "Offline")
    recorder.communication(False, "driver")
    recorder.communication(False, "driver")
    recorder.communication(True, "driver")
    kinds = [row["kind"] for row in store.query(session.id)]
    assert kinds == ["PERDA DE COMUNICAÇÃO", "COMUNICAÇÃO RESTABELECIDA"]


def test_filters_by_variable_event_and_time_window(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.ingest([sample("a", 1, "2026-01-01T00:00:00+00:00"), sample("b", 2, "2026-01-01T00:00:10+00:00")])
    rows = store.query(session.id, variable_id="a", kinds=(TimelineKind.SAMPLE,))
    assert len(rows) == 1 and rows[0]["variable_id"] == "a"
    cursor = rows[0]["timestamp_ns"]
    assert len(TimelineAnalyzer(store).window(session.id, cursor, 1, 1)) == 1


def test_first_deviation_and_recovery_summary(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.deviation("succao", "Primeiro desvio", {"rule": "offline"})
    recorder.recovery("Retorno observado")
    summary = TimelineAnalyzer(store).summary(session.id)
    assert summary["first_deviation"]["message"] == "Primeiro desvio"
    assert summary["recovered"] is True
    assert len(summary["evidence_ids"]) == 2


def test_alarm_is_timeline_evidence(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.alarm("baixa_pressao", True, "Alarme observado")
    row = store.query(session.id)[0]
    assert row["kind"] == "ALARME" and row["value"] is True


def test_correlation_uses_only_recorded_numeric_values(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    for index in range(3):
        timestamp = f"2026-01-01T00:00:0{index}+00:00"
        recorder.ingest([sample("a", index, timestamp), sample("b", index * 2, timestamp)])
    result = TimelineAnalyzer(store).correlation(session.id, "a", "b")
    assert result["pairs"] == 3 and result["coefficient"] == pytest.approx(1.0)


def test_correlation_reports_insufficient_data(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.ingest([sample("a", 1, "2026-01-01T00:00:00+00:00")])
    assert TimelineAnalyzer(store).correlation(session.id, "a", "b")["status"] == "DADOS INSUFICIENTES"


def test_finished_session_is_append_locked(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.stop()
    timestamp, timestamp_ns = high_resolution_timestamp()
    from ipro_bench.field_diagnostics import TimelineRecord
    with pytest.raises(ValueError):
        store.append(session.id, TimelineRecord(TimelineKind.MARKER, timestamp, timestamp_ns))


def test_session_bundle_and_report(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Offline")
    recorder.marker("Inspeção")
    recorder.stop()
    exporter = DiagnosticSessionExporter(store, tmp_path / "out")
    bundle = exporter.export_bundle(session.id)
    report = exporter.report(session.id)
    with zipfile.ZipFile(bundle) as archive:
        payload = json.loads(archive.read("session.json"))
        assert payload["session"]["id"] == session.id
        assert "timeline.csv" in archive.namelist()
    assert report.read_bytes().startswith(b"%PDF-1.4")
