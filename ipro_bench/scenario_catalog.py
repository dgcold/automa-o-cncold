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
                  ScenarioStep(400, ScenarioAction.SET_STATE, parameters={"state": MachineState.RECOVERY.value}),
                  ScenarioStep(410, ScenarioAction.COMMAND_COMPRESSOR, parameters={"enabled": True})]
    if fault:
        steps.append(ScenarioStep(411 if defrost else 130, ScenarioAction.INJECT_FAULT, fault=fault))
    criteria = [TestCriterion("Sem desvio de compressor", "COMPRESSOR_COMANDADO_SEM_RESPOSTA", False)]
    if defrost:
        criteria.append(TestCriterion("Recuperação após degelo", "RECUPERACAO", True))
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
