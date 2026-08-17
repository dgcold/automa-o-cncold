from types import SimpleNamespace

import pytest

from ipro_bench.machine_scan import (
    ENGINEERING_SOURCE, EngineeringPoint, MachineScanAnalyzer, MachineScanRepository,
    Measurement, PipeInput, ReferenceStatus, RefrigerantState, ScanStatus,
    calculate_pipe, classify_refrigerant_state, pressure_absolute_pa, pressure_to_psig,
    select_engineering_reference, thermodynamic_point,
)


def point(chamber=-18, evaporation=-27, pressure=3):
    return EngineeringPoint.create("P01", chamber, {
        "evaporation_temperature_c": evaporation,
        "evaporator_outlet_pressure": pressure,
    })


def measurements(evap=-33, outlet=3, compressor=2, quality="VÁLIDA"):
    return (
        Measurement("chamber_temperature_c", -18, "°C", quality=quality, evidence_ids=(1,)),
        Measurement("evaporation_temperature_c", evap, "°C", quality=quality, evidence_ids=(2,)),
        Measurement("evaporator_outlet_pressure", outlet, "bar", quality=quality, evidence_ids=(3,)),
        Measurement("compressor_inlet_pressure", compressor, "bar", quality=quality, evidence_ids=(4,)),
    )


def scan(rows=None, engineering=None, **kwargs):
    return MachineScanAnalyzer().analyze(engineering or (point(),), rows or measurements(), **kwargs)


def test_real_case_minus_18_minus_27_minus_33():
    result = scan()
    assert [d.value for d in result.deviations] == [-6, 6]


def test_expected_td_is_9_k(): assert scan().deviations[1].engineering_value == 9
def test_observed_td_is_15_k(): assert scan().deviations[1].measured_value == 15
def test_evaporation_deviation_is_minus_6_k(): assert scan().deviations[0].value == -6


def test_normal_evaporator_then_drop_localizes_suction_line():
    result = scan()
    assert result.first_deviation == "LINHA DE SUCÇÃO"
    assert "Entre saída" in result.deviation_location


def test_abnormal_at_evaporator_does_not_call_it_defective():
    result = scan(measurements(outlet=1, compressor=1))
    assert result.first_deviation == "VÁLVULA DE EXPANSÃO / EVAPORADOR"
    assert "DEFEITUOSO" not in result.primary_hypothesis


def test_liquid_line_loss_is_a_hypothesis():
    rows = measurements(outlet=3, compressor=3) + (Measurement("condenser_outlet_subcooling_k", 8, "K"), Measurement("valve_inlet_subcooling_k", 4, "K"))
    result = scan(rows)
    assert next(s for s in result.stages if s.id == "liquid_line").status is ScanStatus.DEVIATION


def test_adequate_subcooling_is_preserved():
    rows = measurements(outlet=3, compressor=3) + (Measurement("condenser_outlet_subcooling_k", 7, "K"), Measurement("valve_inlet_subcooling_k", 6.5, "K"))
    assert next(s for s in scan(rows).stages if s.id == "liquid_line").status is ScanStatus.NORMAL


def test_subcooling_loss_has_checks():
    rows = measurements(outlet=3, compressor=3) + (Measurement("condenser_outlet_subcooling_k", 9, "K"), Measurement("valve_inlet_subcooling_k", 2, "K"))
    assert next(s for s in scan(rows).stages if s.id == "liquid_line").recommendations


def test_high_superheat_is_not_root_cause():
    analyzer = MachineScanAnalyzer(SimpleNamespace())
    result = analyzer.analyze((point(),), measurements(), specialized_results={"superaquecimento": {"valor": 18, "status": "ALTO"}})
    assert result.specialized_results["superaquecimento"]["valor"] == 18 and "CONFIRMADA" not in result.diagnosis


def test_insufficient_data_is_explicit():
    result = MachineScanAnalyzer().analyze((point(),), ())
    assert result.diagnosis == "DIAGNÓSTICO INCONCLUSIVO" and result.confidence is None


def test_invalid_variable_does_not_break_scan():
    result = scan(measurements() + (Measurement("variavel_desconhecida", object()),))
    assert result.id.startswith("VTM-")


def test_bad_quality_is_not_used():
    result = scan(measurements(quality="RUIM"))
    assert result.diagnosis == "DIAGNÓSTICO INCONCLUSIVO"


def test_missing_pressure_requests_both_points():
    rows = measurements()[:2]
    result = scan(rows)
    assert set(result.missing_measurements) == {
        "pressão na saída do evaporador", "temperatura na saída do evaporador",
        "pressão na entrada do compressor", "temperatura na entrada do compressor",
    }


def test_evaporator_can_be_normal():
    result = scan(measurements(evap=-27, outlet=3, compressor=3))
    assert next(s for s in result.stages if s.id == "evaporator").status is ScanStatus.NORMAL


def test_suction_pipe_can_be_normal():
    result = scan(measurements(evap=-27, outlet=3, compressor=3))
    assert next(s for s in result.stages if s.id == "suction_line").status is ScanStatus.NORMAL


def test_multiple_engineering_points_select_exact():
    selected = select_engineering_reference((point(-18), point(-10, -20, 4)), -10)
    assert selected.point_ids == ("P01",) and selected.status is ReferenceStatus.EXACT


def test_reference_is_interpolated_and_labeled():
    selected = select_engineering_reference((point(-20, -29), point(-10, -19)), -15)
    assert selected.status is ReferenceStatus.INTERPOLATED
    assert selected.values["evaporation_temperature_c"].value == -24
    assert selected.values["evaporation_temperature_c"].source == ENGINEERING_SOURCE


def test_outside_envelope_does_not_extrapolate():
    selected = select_engineering_reference((point(-20), point(-10)), 0)
    assert selected.status is ReferenceStatus.OUTSIDE_ENVELOPE and selected.values == {}


def test_inconclusive_diagnosis_never_invents_cause():
    result = scan(measurements()[:2])
    assert result.primary_hypothesis == "NÃO DETERMINADA"


def test_thermal_deviation_without_physical_points_counts_preliminary_stage():
    engineering = (EngineeringPoint.create("P01", -18, {"evaporation_temperature_c": -27}),)
    rows = measurements()[:2]
    result = scan(rows, engineering=engineering)
    assert result.preliminary_stage is ScanStatus.DEVIATION
    assert result.evaluated_stage_count == 1
    assert "1 etapa(s) avaliada(s)" in result.confidence_reason
    assert result.deviation_location == "NÃO DETERMINADA"


def test_inconclusive_location_always_requests_priority_measurements_and_explains_purpose():
    engineering = (EngineeringPoint.create("P01", -18, {"evaporation_temperature_c": -27}),)
    result = scan(measurements()[:2], engineering=engineering)
    assert result.missing_measurements == (
        "pressão na saída do evaporador", "temperatura na saída do evaporador",
        "pressão na entrada do compressor", "temperatura na entrada do compressor",
    )
    assert "já ocorre no evaporador" in result.missing_measurements_purpose
    assert "DADOS ADICIONAIS NECESSÁRIOS" in result.diagnosis
    assert result.localization_reason == "Faltam medições entre evaporador e compressor."


def test_first_deviation_is_reported(): assert scan().first_deviation == "LINHA DE SUCÇÃO"


def test_coil_specialized_result_is_integrated_without_duplication():
    result = scan(specialized_results={"serpentina_aletada": {"status": "DADO DE ENGENHARIA AUSENTE"}})
    assert tuple(result.specialized_results) == ("serpentina_aletada",)


def test_defrost_result_is_consumed_as_specialized_result():
    result = scan(specialized_results={"analise_de_degelo": {"conclusao": "DEGELO NORMAL", "evidencias": [8]}})
    assert result.specialized_results["analise_de_degelo"]["conclusao"] == "DEGELO NORMAL"


def test_ai_is_after_deterministic_scan_and_does_not_replace_defrost():
    specialized = {"analise_de_degelo": {"conclusao": "INCOMPLETO"}, "analise_ia": {"correlacao": "compatível", "causa": "NÃO DETERMINADA"}}
    result = scan(specialized_results=specialized)
    assert set(result.specialized_results) == {"analise_de_degelo", "analise_ia"}


def test_session_change_does_not_inherit_previous_scan(tmp_path):
    repository = MachineScanRepository(tmp_path / "scans.sqlite3")
    first = scan(session_id="DIA-1"); second = scan(session_id="DIA-2")
    repository.save(first); repository.save(second)
    assert [item["session_id"] for item in repository.list("DIA-2")] == ["DIA-2"]


def test_pipe_calculation_and_two_phase_guard():
    valid = calculate_pipe(PipeInput(.022, .001, 10, 2, .1, 900, .02, 1, RefrigerantState.SUBCOOLED_LIQUID))
    blocked = calculate_pipe(PipeInput(refrigerant_state=RefrigerantState.SATURATION))
    assert valid.applicable and valid.internal_diameter_m == pytest.approx(.02) and not blocked.applicable


def test_refrigerant_state_requires_thermodynamic_data():
    reading = SimpleNamespace(saturation_temperature_c=None, line_temperature_c=5, name="SUPERAQUECIMENTO")
    assert classify_refrigerant_state(reading) is RefrigerantState.UNDETERMINED


def four_thermal_measurements(unit="PSIG"):
    return measurements()[:2] + (
        Measurement("evaporator_outlet_pressure", 30, unit), Measurement("evaporator_outlet_temperature_c", -21, "°C"),
        Measurement("compressor_inlet_pressure", 21, unit), Measurement("compressor_inlet_temperature_c", -19, "°C"),
    )


def thermal_engineering():
    return (EngineeringPoint.create("P01", -18, {"evaporation_temperature_c": -27}),)


def test_four_measurements_with_unavailable_properties_are_not_missing(monkeypatch):
    monkeypatch.setattr("ipro_bench.machine_scan.temperatura_saturacao_c", lambda *_args, **_kwargs: None)
    result = scan(four_thermal_measurements(), engineering=thermal_engineering(), refrigerant="R410A")
    assert result.missing_measurements == ()
    assert "Medições disponíveis" in result.localization_reason
    assert result.continuation_requirement.startswith("Disponibilizar propriedades")


def test_complete_measurements_never_report_missing_measurements(monkeypatch):
    monkeypatch.setattr("ipro_bench.machine_scan.temperatura_saturacao_c", lambda *_args, **_kwargs: None)
    result = scan(four_thermal_measurements(), engineering=thermal_engineering(), refrigerant="R410A")
    assert "Faltam medições" not in result.localization_reason


def test_available_properties_enable_physical_location(monkeypatch):
    monkeypatch.setattr("ipro_bench.machine_scan.temperatura_saturacao_c", lambda pressure, *_args, **_kwargs: -27 if pressure >= 30 else -33)
    result = scan(four_thermal_measurements(), engineering=thermal_engineering(), refrigerant="R410A")
    assert result.first_deviation == "LINHA DE SUCÇÃO"
    assert all(item.status == "CALCULADO" for item in result.thermodynamic_points)


@pytest.mark.parametrize(("value", "unit"), ((10, "PSIG"), (0.6894757, "bar(g)"), (68.94757, "kPa(g)")))
def test_pressure_units_convert_to_same_psig(value, unit):
    assert pressure_to_psig(value, unit) == pytest.approx(10, rel=1e-5)


def test_gauge_pressure_is_converted_to_correct_absolute_pressure():
    assert pressure_absolute_pa(30, "PSIG") == pytest.approx((30 + 14.6959) * 6894.757293168)


def test_unknown_refrigerant_is_not_queried_as_confirmed():
    item = thermodynamic_point("PONTO", Measurement("p", 30, "PSIG"), Measurement("t", -20, "°C"), "R-FICTÍCIO")
    assert item.status == "REFRIGERANTE NÃO CONFIRMADO" and item.saturation_temperature_c is None


def test_invalid_pressure_does_not_reach_thermodynamic_model():
    item = thermodynamic_point("PONTO", Measurement("p", -20, "PSIG"), Measurement("t", -20, "°C"), "R410A")
    assert item.status == "PRESSÃO INVÁLIDA" and item.pressure_absolute_pa is None


def test_thermodynamic_result_is_traceable(monkeypatch):
    monkeypatch.setattr("ipro_bench.machine_scan.temperatura_saturacao_c", lambda *_args, **_kwargs: -25.0)
    item = thermodynamic_point("SAÍDA DO EVAPORADOR", Measurement("p", 30, "PSIG"), Measurement("t", -21, "°C"), "R410A")
    assert item.pressure_gauge == 30 and item.pressure_gauge_psig == 30
    assert item.pressure_absolute_pa == pytest.approx((30 + 14.6959) * 6894.757293168)
    assert item.saturation_temperature_c == -25 and item.measured_temperature_c == -21 and item.superheat_k == 4
