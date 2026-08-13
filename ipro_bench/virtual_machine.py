from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum


class MachineState(StrEnum):
    STOPPED = "PARADA"
    STARTING = "PARTIDA"
    COOLING = "RESFRIAMENTO"
    STABLE = "ESTÁVEL"
    DEFROST = "DEGELO"
    DRIPPING = "GOTEJAMENTO"
    RETURNING = "RETORNO_REFRIGERACAO"
    RECOVERY = "RECUPERACAO"
    FAILURE = "FALHA"
    PROTECTION = "PROTECAO"


@dataclass
class VirtualRefrigerationMachine:
    """Deterministic, hardware-free refrigeration process model."""

    seed: int = 1
    state: MachineState = MachineState.STOPPED
    chamber_temperature: float = 8.0
    evaporator_temperature: float = 6.0
    suction_pressure: float = 90.0
    discharge_pressure: float = 90.0
    compressor_command: bool = False
    compressor: bool = False
    evaporator_fan: bool = False
    condenser_fan: bool = False
    defrost: bool = False
    dripping: bool = False
    communication: bool = True
    alarms: set[str] = field(default_factory=set)
    faults: set[str] = field(default_factory=set)
    elapsed: float = 0.0
    state_elapsed: float = 0.0
    _rng: random.Random = field(init=False, repr=False)
    _frozen_sensor: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def transition(self, state: MachineState) -> None:
        if state is self.state:
            return
        self.state = state
        self.state_elapsed = 0.0
        if state is MachineState.STOPPED:
            self.compressor_command = self.compressor = False
            self.evaporator_fan = self.condenser_fan = False
            self.defrost = self.dripping = False
        elif state is MachineState.STARTING:
            self.compressor_command = True
            self.defrost = self.dripping = False
        elif state in (MachineState.COOLING, MachineState.STABLE, MachineState.RECOVERY):
            self.compressor_command = True
            self.evaporator_fan = self.condenser_fan = True
            self.defrost = self.dripping = False
        elif state is MachineState.DEFROST:
            self.compressor_command = self.compressor = False
            self.evaporator_fan = self.condenser_fan = False
            self.defrost, self.dripping = True, False
        elif state is MachineState.DRIPPING:
            self.compressor_command = self.compressor = False
            self.evaporator_fan = self.condenser_fan = False
            self.defrost, self.dripping = False, True
        elif state is MachineState.RETURNING:
            self.compressor_command = False
            self.defrost = self.dripping = False

    def command_compressor(self, enabled: bool) -> None:
        self.compressor_command = enabled

    def inject_fault(self, fault: str) -> None:
        self.faults.add(fault.upper())
        if fault.upper() == "SENSOR_TRAVADO":
            self._frozen_sensor = self.chamber_temperature

    def clear_fault(self, fault: str) -> None:
        self.faults.discard(fault.upper())
        if fault.upper() == "SENSOR_TRAVADO":
            self._frozen_sensor = None

    def tick(self, seconds: float) -> None:
        dt = max(0.0, float(seconds))
        self.elapsed += dt
        self.state_elapsed += dt
        blocked = {"COMPRESSOR_NAO_LIGA", "COMPRESSOR_NAO_RETORNA_POS_DEGELO", "FALHA_ELETRICA"}
        unexpected_off = "COMPRESSOR_DESLIGA" in self.faults
        self.compressor = self.compressor_command and not (self.faults & blocked) and not unexpected_off
        if "VENTILADOR_EVAPORADOR_FALHA" in self.faults:
            self.evaporator_fan = False
        if "VENTILADOR_CONDENSADOR_FALHA" in self.faults:
            self.condenser_fan = False
        rate = dt / 60.0
        noise = self._rng.uniform(-0.015, 0.015)
        if self.defrost:
            factor = 0.25 if "DEGELO_INCOMPLETO" in self.faults else 1.0
            self.evaporator_temperature += 5.0 * rate * factor
            self.chamber_temperature += 0.15 * rate
            self.suction_pressure += (30.0 - self.suction_pressure) * min(1.0, 0.08 * dt)
            self.discharge_pressure += (220.0 - self.discharge_pressure) * min(1.0, 0.05 * dt)
        elif self.compressor:
            slow = 0.2 if "RECUPERACAO_LENTA" in self.faults else 1.0
            self.chamber_temperature += (-0.55 * rate * slow) + noise
            self.evaporator_temperature += (-1.4 * rate * slow) + noise
            self.suction_pressure += (20.0 - self.suction_pressure) * min(1.0, 0.04 * dt)
            target_discharge = 360.0 if "ALTA_PRESSAO" in self.faults else 245.0
            self.discharge_pressure += (target_discharge - self.discharge_pressure) * min(1.0, 0.04 * dt)
        else:
            self.chamber_temperature += (12.0 - self.chamber_temperature) * min(1.0, 0.002 * dt)
            self.evaporator_temperature += (self.chamber_temperature - self.evaporator_temperature) * min(1.0, 0.01 * dt)
            self.suction_pressure += (90.0 - self.suction_pressure) * min(1.0, 0.02 * dt)
            self.discharge_pressure += (90.0 - self.discharge_pressure) * min(1.0, 0.02 * dt)
        if "BAIXA_PRESSAO" in self.faults:
            self.suction_pressure = min(self.suction_pressure, 5.0)
        self.communication = "PERDA_COMUNICACAO" not in self.faults
        if "COMUNICACAO_INTERMITENTE" in self.faults:
            self.communication = int(self.elapsed) % 10 < 6
        self._update_alarms()

    def _update_alarms(self) -> None:
        alarms: set[str] = set()
        if self.discharge_pressure >= 330:
            alarms.add("ALTA_PRESSAO")
        if self.suction_pressure <= 7:
            alarms.add("BAIXA_PRESSAO")
        if self.chamber_temperature >= 15:
            alarms.add("ALTA_TEMPERATURA")
        if "SENSOR_INVALIDO" in self.faults or "SENSOR_ABERTO" in self.faults or "SENSOR_CURTO" in self.faults:
            alarms.add("FALHA_SENSOR")
        self.alarms = alarms

    def sensor_value(self, name: str) -> float | None:
        if name == "temperature_chamber" and self._frozen_sensor is not None:
            return self._frozen_sensor
        if name == "temperature_chamber" and self.faults & {"SENSOR_INVALIDO", "SENSOR_ABERTO", "SENSOR_CURTO"}:
            return None
        return {
            "temperature_chamber": self.chamber_temperature,
            "temperature_evaporator": self.evaporator_temperature,
            "pressure_suction": self.suction_pressure,
            "pressure_discharge": self.discharge_pressure,
        }[name]
