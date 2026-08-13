import json
from dataclasses import replace
from pathlib import Path

import pytest

from ipro_bench.application import build_application_services
from ipro_bench.drivers.em210 import EM210Role
from ipro_bench.settings import ApplicationSettings
from ipro_bench.structured_logging import TechnicalError


@pytest.fixture
def project_dir():
    return Path(__file__).resolve().parents[1]


def test_application_settings_are_external_and_safe(project_dir):
    settings = ApplicationSettings.load(project_dir / "config" / "application.json")
    assert settings.ipro.allowed_functions == (3, 4)
    assert settings.ipro.automatic_connection is False
    assert settings.rs485.automatic_start is False


def test_settings_reject_automatic_real_connection(project_dir):
    settings = ApplicationSettings.load(project_dir / "config" / "application.json")
    with pytest.raises(ValueError, match="automática"):
        replace(settings, ipro=replace(settings.ipro, automatic_connection=True)).validate()


def test_settings_reject_write_function(project_dir):
    settings = ApplicationSettings.load(project_dir / "config" / "application.json")
    with pytest.raises(ValueError, match="FC03/FC04"):
        replace(settings, ipro=replace(settings.ipro, allowed_functions=(3, 4, 6))).validate()


def test_application_composition_does_not_activate_transport(project_dir):
    services = build_application_services(project_dir)
    assert services.rs485.active is False
    assert all(driver.transport_active is False for driver in services.controllers.all())
    assert all(driver.transport_active is False for driver in services.em210_drivers)
    assert services.blackbox.session is None


def test_em210_drivers_have_two_roles_and_empty_official_maps(project_dir):
    drivers = build_application_services(project_dir).em210_drivers
    assert {driver.role for driver in drivers} == {EM210Role.MACHINE_TOTAL, EM210Role.COMPRESSOR}
    assert all(driver.official_map()["variables"] == [] for driver in drivers)
    assert all(driver.normalized_variables() == () for driver in drivers)


def test_em210_diagnostics_are_honest(project_dir):
    for driver in build_application_services(project_dir).em210_drivers:
        diagnostic = driver.diagnostic()
        assert diagnostic["state"] == "NÃO CONECTADO"
        assert diagnostic["data"] == "SEM DADOS"
        assert diagnostic["map"] == "AGUARDANDO DRIVER/MAPA OFICIAL"


def test_technical_error_contains_required_context():
    error = TechnicalError.from_exception(
        "driver.ipro", "read", TimeoutError("timeout"),
        equipment="iPro", transport="Modbus TCP", endpoint="offline",
        classification="TIMEOUT",
    )
    payload = json.loads(error.to_json())
    assert all(payload[field] for field in ("module", "operation", "equipment", "transport", "endpoint", "exception", "classification", "timestamp"))


def test_no_absolute_development_paths_in_product(project_dir):
    for path in (project_dir / "ipro_bench").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in text and "C:/Users/" not in text


def test_official_and_candidate_maps_remain_separate(project_dir):
    services = build_application_services(project_dir)
    ipro = services.controllers.get("ipro")
    assert ipro.official_map_path != ipro.candidate_map_path
    assert ipro.load_official_map()["variables"] == []
    assert json.loads(ipro.candidate_map_path.read_text(encoding="utf-8"))["variables"]


def test_ui_has_no_direct_serial_or_modbus_implementation(project_dir):
    source = (project_dir / "ipro_bench" / "ui.py").read_text(encoding="utf-8")
    assert "serial.Serial(" not in source
    assert "write_register" not in source and "write_coil" not in source
    assert "ModbusTcpClient" not in source


def test_query_limits_are_positive(project_dir):
    analysis = ApplicationSettings.load(project_dir / "config" / "application.json").analysis
    assert analysis.history_page_limit > 0 and analysis.export_limit > 0 and analysis.timeline_limit > 0


def test_final_version(project_dir):
    import ipro_bench
    assert ipro_bench.__version__ == "1.0.0"
