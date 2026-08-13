import json

import pytest

from ipro_bench.drivers.base import DriverState, MapStatus
from ipro_bench.drivers.fullgauge_vx1050e import FullGaugeVX1050EDriver
from ipro_bench.drivers.ipro import IProDriver
from ipro_bench.drivers.registry import ControllerRegistry, build_default_registry


def test_default_registry_has_two_independent_controllers(project_dir):
    registry = build_default_registry(project_dir)
    assert [driver.identity.id for driver in registry.all()] == ["ipro", "fullgauge_vx1050e"]
    assert registry.get("ipro") is not registry.get("fullgauge_vx1050e")


def test_controller_selection_is_offline_and_has_no_variables(project_dir):
    for driver in build_default_registry(project_dir).all():
        snapshot = driver.snapshot()
        assert snapshot.state is DriverState.NOT_CONNECTED
        assert snapshot.transport_active is False
        assert snapshot.variables == ()
        assert snapshot.diagnostic.startswith("SEM MAPA · SEM DADOS")


def test_both_official_maps_are_empty_and_waiting(project_dir):
    for driver in build_default_registry(project_dir).all():
        payload = driver.load_official_map()
        assert payload["variables"] == []
        assert payload["metadata"]["kind"] == "OFFICIAL"
        assert payload["metadata"]["status"] == MapStatus.WAITING_OFFICIAL.value


def test_ipro_candidates_are_separate_from_official_map(project_dir):
    driver = IProDriver(project_dir)
    assert driver.candidate_map_path != driver.official_map_path
    candidate = json.loads(driver.candidate_map_path.read_text(encoding="utf-8"))
    official = driver.load_official_map()
    assert candidate["variables"]
    assert official["variables"] == []


@pytest.mark.parametrize("function", [5, 6, 15, 16])
def test_ipro_driver_blocks_write_functions(project_dir, function):
    with pytest.raises(PermissionError):
        IProDriver(project_dir).validate_function(function)


@pytest.mark.parametrize("function", [3, 4])
def test_ipro_driver_accepts_read_functions(project_dir, function):
    IProDriver(project_dir).validate_function(function)


def test_vx_driver_does_not_invent_transport_or_map(project_dir):
    driver = FullGaugeVX1050EDriver(project_dir)
    assert driver.identity.protocol == "AGUARDANDO DEFINIÇÃO OFICIAL"
    assert driver.normalized_variables() == ()
    assert driver.communication_diagnostic()["transport_active"] is False


def test_registry_rejects_duplicate_driver(project_dir):
    driver = IProDriver(project_dir)
    registry = ControllerRegistry([driver])
    with pytest.raises(ValueError):
        registry.register(driver)


@pytest.fixture
def project_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
