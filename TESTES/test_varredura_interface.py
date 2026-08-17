from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

import ipro_bench.machine_scan as machine_scan
from ipro_bench.ui import MainWindow


def window(tmp_path: Path):
    shutil.copytree(Path("config"), tmp_path / "config")
    app = QApplication.instance() or QApplication([])
    return app, MainWindow(tmp_path)


def test_four_manual_fields_reach_existing_deterministic_engine(tmp_path, monkeypatch):
    app, ui = window(tmp_path)
    captured = {}
    original = ui.machine_scan_analyzer.analyze

    def spy(points, measurements, **kwargs):
        captured["measurements"] = measurements
        captured["kwargs"] = kwargs
        return original(points, measurements, **kwargs)

    monkeypatch.setattr(ui.machine_scan_analyzer, "analyze", spy)
    monkeypatch.setattr(ui.tcp, "test_connection", lambda: pytest.fail("A varredura iniciou comunicação TCP real."))
    monkeypatch.setattr(ui.tcp, "read", lambda *args: pytest.fail("A varredura iniciou leitura TCP real."))
    try:
        ui.scan_evap_out_pressure.setText("30")
        ui.scan_evap_out_temperature.setText("-24")
        ui.scan_comp_in_pressure.setText("20")
        ui.scan_comp_in_temperature.setText("-27")
        ui.scan_refrigerant.setCurrentText("R404A")
        ui._run_machine_scan(); app.processEvents()
        names = {item.name for item in captured["measurements"]}
        assert names >= {"evaporator_outlet_pressure", "evaporator_outlet_temperature_c", "compressor_inlet_pressure", "compressor_inlet_temperature_c"}
        assert captured["kwargs"]["refrigerant"] == "R404A"
        assert not ui.rs485.active
    finally:
        ui.close()


def test_empty_manual_fields_remain_missing_and_do_not_inherit_previous_run(tmp_path, monkeypatch):
    app, ui = window(tmp_path)
    monkeypatch.setattr(ui.tcp, "test_connection", lambda: pytest.fail("A varredura iniciou comunicação TCP real."))
    monkeypatch.setattr(ui.tcp, "read", lambda *args: pytest.fail("A varredura iniciou leitura TCP real."))
    try:
        for field, value in ((ui.scan_evap_out_pressure, "30"), (ui.scan_evap_out_temperature, "-24"), (ui.scan_comp_in_pressure, "20"), (ui.scan_comp_in_temperature, "-27")): field.setText(value)
        ui._run_machine_scan()
        for field in (ui.scan_evap_out_pressure, ui.scan_evap_out_temperature, ui.scan_comp_in_pressure, ui.scan_comp_in_temperature): field.clear()
        ui._run_machine_scan(); app.processEvents()
        latest = ui.machine_scan_repository.list()[0]
        assert len(latest["measurements"]) == 2
        assert len(latest["missing_measurements"]) == 4
        assert "DADOS ADICIONAIS NECESSÁRIOS" in latest["diagnosis"]
        assert not ui.rs485.active
    finally:
        ui.close()


def test_filled_pressures_advance_location_when_properties_are_available(tmp_path, monkeypatch):
    monkeypatch.setattr(machine_scan, "temperatura_saturacao_c", lambda pressure, refrigerant, qualidade: -27.0 if pressure >= 30 else -33.0)
    app, ui = window(tmp_path)
    try:
        ui.scan_refrigerant.setCurrentText("R404A")
        ui.scan_evap_out_pressure.setText("30"); ui.scan_evap_out_temperature.setText("-24")
        ui.scan_comp_in_pressure.setText("20"); ui.scan_comp_in_temperature.setText("-27")
        ui._run_machine_scan(); app.processEvents()
        latest = ui.machine_scan_repository.list()[0]
        assert latest["first_deviation"] == "LINHA DE SUCÇÃO"
        assert "Entre saída do evaporador" in latest["deviation_location"]
        assert latest["missing_measurements"] == []
    finally:
        ui.close()


def test_pressure_without_refrigerant_is_recorded_without_unsafe_conversion(tmp_path):
    app, ui = window(tmp_path)
    try:
        ui.scan_evap_out_pressure.setText("30"); ui.scan_evap_out_temperature.setText("-24")
        ui.scan_comp_in_pressure.setText("20"); ui.scan_comp_in_temperature.setText("-27")
        ui.scan_refrigerant.setCurrentIndex(0)
        ui._run_machine_scan(); app.processEvents()
        latest = ui.machine_scan_repository.list()[0]
        assert "não foi possível convertê-las" in latest["thermodynamic_note"]
        assert latest["first_deviation"] == "NÃO LOCALIZADO"
    finally:
        ui.close()


@pytest.mark.parametrize("width,height", ((1366, 768), (1600, 900), (1920, 1080)))
def test_scan_page_scroll_exposes_map_and_complete_result_at_supported_sizes(tmp_path, width, height):
    app, ui = window(tmp_path)
    try:
        ui.resize(width, height)
        ui.navigation.setCurrentRow(ui.navigation.count() - 1)
        ui.show(); ui._run_machine_scan(); app.processEvents()
        scroll = ui.scan_scroll_area.verticalScrollBar()
        assert ui.scan_scroll_area.widgetResizable()
        assert scroll.maximum() > 0
        assert ui.scan_map.rowCount() == 9
        assert ui.scan_map.height() >= 300
        assert ui.scan_map.verticalScrollBarPolicy().name == "ScrollBarAlwaysOff"
        assert "DIAGNÓSTICO" in ui.scan_result.toPlainText()
        ui.scan_scroll_area.ensureWidgetVisible(ui.scan_result, 0, 0); app.processEvents()
        assert scroll.value() > 0
        scroll.setValue(scroll.maximum()); app.processEvents()
        assert scroll.value() == scroll.maximum()
    finally:
        ui.close()
