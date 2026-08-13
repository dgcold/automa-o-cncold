from __future__ import annotations

from dataclasses import dataclass

from .virtual_machine import VirtualRefrigerationMachine

FAULT_CATALOG = frozenset({
    "COMPRESSOR_NAO_LIGA", "COMPRESSOR_DESLIGA", "COMPRESSOR_NAO_RETORNA_POS_DEGELO",
    "VENTILADOR_EVAPORADOR_FALHA", "VENTILADOR_CONDENSADOR_FALHA", "SENSOR_TRAVADO",
    "SENSOR_INVALIDO", "SENSOR_ABERTO", "SENSOR_CURTO", "ALTA_PRESSAO", "BAIXA_PRESSAO",
    "DEGELO_INCOMPLETO", "RECUPERACAO_LENTA", "PERDA_COMUNICACAO",
    "COMUNICACAO_INTERMITENTE", "CORRENTE_ELEVADA", "DESEQUILIBRIO_FASES", "FALHA_ELETRICA",
})


@dataclass(frozen=True)
class InjectedFault:
    name: str
    timestamp: str


class FaultInjector:
    def __init__(self, machine: VirtualRefrigerationMachine) -> None:
        self.machine = machine
        self.injected: list[InjectedFault] = []

    def inject(self, name: str, timestamp: str) -> InjectedFault:
        key = name.upper()
        if key not in FAULT_CATALOG:
            raise ValueError(f"Falha simulada desconhecida: {name}")
        self.machine.inject_fault(key)
        item = InjectedFault(key, timestamp)
        self.injected.append(item)
        return item

    def clear(self, name: str) -> None:
        self.machine.clear_fault(name.upper())
