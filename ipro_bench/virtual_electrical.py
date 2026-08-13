from __future__ import annotations

import random
from dataclasses import dataclass

from .core import DataQuality
from .telemetry import TelemetrySample
from .virtual_machine import MachineState, VirtualRefrigerationMachine


@dataclass
class VirtualElectricalInstrumentation:
    seed: int = 1
    total_available: bool = True
    compressor_available: bool = True

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed + 1000)

    def samples(self, machine: VirtualRefrigerationMachine, timestamp: str, metadata: dict) -> tuple[TelemetrySample, ...]:
        starting = machine.state is MachineState.STARTING and machine.compressor
        compressor = 0.15 if not machine.compressor else (42.0 if starting else 12.0)
        if "CORRENTE_ELEVADA" in machine.faults:
            compressor = 22.0
        total = compressor + (3.0 if machine.evaporator_fan else 0.0) + (4.0 if machine.condenser_fan else 0.0) + (8.0 if machine.defrost else 0.0)
        phases = [total / 3.0] * 3
        if "DESEQUILIBRIO_FASES" in machine.faults:
            phases = [total * 0.52, total * 0.31, total * 0.17]
        values = {
            "current_total": total if self.total_available else None,
            "current_compressor": compressor if self.compressor_available else None,
            "current_l1": phases[0] if self.total_available else None,
            "current_l2": phases[1] if self.total_available else None,
            "current_l3": phases[2] if self.total_available else None,
        }
        names = {
            "current_total": "Corrente total da máquina", "current_compressor": "Corrente do compressor",
            "current_l1": "Corrente L1", "current_l2": "Corrente L2", "current_l3": "Corrente L3",
        }
        return tuple(TelemetrySample(key, names[key], "MEDIÇÃO ELÉTRICA", "A",
            round(value + self._rng.uniform(-0.02, 0.02), 3) if value is not None else None,
            DataQuality.VALID if value is not None else DataQuality.NO_DATA, "SIMULADOR", True,
            timestamp, {**metadata, "instrument": "EM210 #1 - TOTAL" if key != "current_compressor" else "EM210 #2 - COMPRESSOR"})
            for key, value in values.items())
