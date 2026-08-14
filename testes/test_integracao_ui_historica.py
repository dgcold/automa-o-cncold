from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ipro_bench.core import DataQuality
from ipro_bench.telemetry import TelemetrySample


pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from ipro_bench.ui import MainWindow


def _sample(value: float, timestamp: str) -> TelemetrySample:
    return TelemetrySample(
        "temperature_chamber", "Temperatura da câmara", "SENSORES", "°C",
        value, DataQuality.VALID, "SIMULADOR", True, timestamp,
    )


def _session(window: MainWindow, name: str, first: float, second: float) -> str:
    session = window.blackbox.start("simulator", name)
    window.blackbox.ingest((_sample(first, "2026-08-13T10:00:00-03:00"),))
    window.blackbox.ingest((_sample(second, "2026-08-13T10:00:05-03:00"),))
    window.blackbox.stop()
    return session.id


def test_historical_selection_propagates_and_clears_stale_views(tmp_path: Path) -> None:
    shutil.copytree(Path("config"), tmp_path / "config")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    try:
        session_a = _session(window, "DIA A", 1.0, 2.0)
        session_b = _session(window, "DIA B", 8.0, 9.0)
        window._refresh_sessions()
        window.ai_explanation.setText("RESULTADO ANTIGO")

        rows_by_id = {
            window.sessions_table.item(row, 0).text(): row
            for row in range(window.sessions_table.rowCount())
        }
        window.sessions_table.selectRow(rows_by_id[session_a])
        app.processEvents()
        assert window.historical_session_id == session_a
        assert window.sensor_chart.values == [1.0, 2.0]
        assert window.timeline_table.rowCount() >= 3
        assert window.incident_event.text().isdigit()
        assert window.diagnostic_session.text() == session_a
        assert window.ai_session.text() == session_a
        assert "RESULTADO ANTIGO" not in window.ai_explanation.text()

        window.sessions_table.selectRow(rows_by_id[session_b])
        app.processEvents()
        assert window.historical_session_id == session_b
        assert window.sensor_chart.values == [8.0, 9.0]
        assert window.diagnostic_session.text() == session_b
        assert window.ai_session.text() == session_b
        assert not window.rs485.active
    finally:
        window.close()
