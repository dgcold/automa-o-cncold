from __future__ import annotations

from .scenarios import Scenario, ScenarioAction, ScenarioStep, TestCriterion
from .virtual_machine import MachineState


def _scenario(name: str, fault: str | None = None, *, defrost: bool = False) -> Scenario:
    steps = [
        ScenarioStep(0, ScenarioAction.SET_STATE, parameters={"state": MachineState.STOPPED.value}),
        ScenarioStep(10, ScenarioAction.SET_STATE, parameters={"state": MachineState.STARTING.value}),
        ScenarioStep(20, ScenarioAction.SET_STATE, parameters={"state": MachineState.COOLING.value}),
        ScenarioStep(120, ScenarioAction.SET_STATE, parameters={"state": MachineState.STABLE.value}),
    ]
    if defrost:
        steps += [ScenarioStep(300, ScenarioAction.SET_STATE, parameters={"state": MachineState.DEFROST.value}),
                  ScenarioStep(360, ScenarioAction.SET_STATE, parameters={"state": MachineState.DRIPPING.value}),
                  ScenarioStep(390, ScenarioAction.SET_STATE, parameters={"state": MachineState.RETURNING.value}),
                  ScenarioStep(400, ScenarioAction.SET_STATE, parameters={"state": MachineState.RECOVERY.value})]
        if fault == "COMPRESSOR_NAO_RETORNA_POS_DEGELO":
            steps.append(ScenarioStep(409, ScenarioAction.INJECT_FAULT, fault=fault))
        steps.append(ScenarioStep(410, ScenarioAction.COMMAND_COMPRESSOR, parameters={"enabled": True}))
        if fault != "COMPRESSOR_NAO_RETORNA_POS_DEGELO":
            steps.append(ScenarioStep(600, ScenarioAction.SET_STATE, parameters={"state": MachineState.STABLE.value}))
    if fault:
        if fault != "COMPRESSOR_NAO_RETORNA_POS_DEGELO":
            fault_time = 305 if fault == "DEGELO_INCOMPLETO" else (411 if defrost else 130)
            steps.append(ScenarioStep(fault_time, ScenarioAction.INJECT_FAULT, fault=fault))
    criteria_by_fault = {
        "COMPRESSOR_NAO_RETORNA_POS_DEGELO": TestCriterion(
            "Falha de retorno do compressor reproduzida", "COMPRESSOR_COMANDADO_SEM_RESPOSTA"
        ),
        "COMPRESSOR_NAO_LIGA": TestCriterion(
            "Compressor comandado sem resposta", "COMPRESSOR_COMANDADO_SEM_RESPOSTA"
        ),
        "VENTILADOR_CONDENSADOR_FALHA": TestCriterion(
            "Ventilador do condensador sem resposta", "", evidence_family="condenser_fan_without_feedback"
        ),
        "SENSOR_INVALIDO": TestCriterion(
            "Leitura inválida do sensor detectada", "", evidence_family="invalid_sensor_reading"
        ),
        "PERDA_COMUNICACAO": TestCriterion(
            "Perda de comunicação detectada", "", evidence_family="communication_loss_observed"
        ),
        "DEGELO_INCOMPLETO": TestCriterion(
            "Ciclo de degelo incompleto detectado", "", evidence_family="incomplete_defrost_cycle"
        ),
        "RECUPERACAO_LENTA": TestCriterion(
            "Recuperação térmica lenta detectada", "", evidence_family="slow_thermal_recovery"
        ),
        "CORRENTE_ELEVADA": TestCriterion(
            "Corrente elevada do compressor detectada", "", evidence_family="high_compressor_current"
        ),
        "DESEQUILIBRIO_FASES": TestCriterion(
            "Desequilíbrio entre fases detectado", "", evidence_family="phase_current_imbalance"
        ),
    }
    criteria = [criteria_by_fault[fault]] if fault else [
        TestCriterion("Operação sem anomalia relevante", "", should_exist=False, evidence_family="*")
    ]
    return Scenario(name, "Cenário estruturado offline · origem SIMULADOR", steps=steps,
                    criteria=criteria, duration_seconds=700 if defrost else 240)


def default_scenarios() -> tuple[Scenario, ...]:
    return (
        _scenario("TESTE 01 - FALHA DE RECUPERACAO POS-DEGELO", "COMPRESSOR_NAO_RETORNA_POS_DEGELO", defrost=True),
        _scenario("TESTE 02 - OPERAÇÃO NORMAL"),
        _scenario("TESTE 03 - COMPRESSOR NÃO PARTE", "COMPRESSOR_NAO_LIGA"),
        _scenario("TESTE 04 - VENTILADOR CONDENSADOR FALHA", "VENTILADOR_CONDENSADOR_FALHA"),
        _scenario("TESTE 05 - SENSOR INVÁLIDO", "SENSOR_INVALIDO"),
        _scenario("TESTE 06 - PERDA DE COMUNICAÇÃO", "PERDA_COMUNICACAO"),
        _scenario("TESTE 07 - DEGELO INCOMPLETO", "DEGELO_INCOMPLETO", defrost=True),
        _scenario("TESTE 08 - RECUPERAÇÃO LENTA", "RECUPERACAO_LENTA", defrost=True),
        _scenario("TESTE 09 - CORRENTE DO COMPRESSOR ELEVADA", "CORRENTE_ELEVADA"),
        _scenario("TESTE 10 - DESEQUILÍBRIO DE FASES", "DESEQUILIBRIO_FASES"),
    )
