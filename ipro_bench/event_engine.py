from __future__ import annotations

from .field_diagnostics import BlackBoxRecorder
from .virtual_machine import MachineState, VirtualRefrigerationMachine

STATE_MARKERS = {
    MachineState.DEFROST: "DEGELO_INICIO",
    MachineState.DRIPPING: "DEGELO_FIM",
    MachineState.RETURNING: "GOTEJAMENTO_FIM",
    MachineState.RECOVERY: "RETORNO_REFRIGERACAO",
}


class EventEngine:
    def __init__(self, recorder: BlackBoxRecorder) -> None:
        self.recorder = recorder
        self._state: MachineState | None = None
        self._alarms: set[str] = set()
        self._communication: bool | None = None
        self._mismatch_since: float | None = None
        self.first_deviation_recorded = False
        self.events: list[dict] = []

    def observe(self, machine: VirtualRefrigerationMachine, timestamp: str, elapsed: float) -> None:
        if machine.state is not self._state:
            previous = self._state
            marker = STATE_MARKERS.get(machine.state)
            if marker:
                self.recorder.marker(marker, f"Estado {machine.state.value}", timestamp=timestamp)
                self.events.append({"timestamp": timestamp, "event": marker})
            if machine.state is MachineState.STABLE and previous is MachineState.RECOVERY:
                self.recorder.recovery("Recuperação operacional observada", {"source": "SIMULADOR"}, timestamp)
                self.recorder.marker("RECUPERACAO", timestamp=timestamp)
                self.events.append({"timestamp": timestamp, "event": "RECUPERACAO"})
            self._state = machine.state
        if self._communication is None:
            self._communication = machine.communication
        elif machine.communication != self._communication:
            self.recorder.communication(machine.communication, "SIMULADOR", timestamp=timestamp)
            self.events.append({"timestamp": timestamp, "event": "COMUNICACAO_RESTABELECIDA" if machine.communication else "PERDA_COMUNICACAO"})
            self._communication = machine.communication
        for alarm in sorted(machine.alarms - self._alarms):
            self.recorder.alarm(alarm, True, f"{alarm} simulado", timestamp=timestamp)
            self.events.append({"timestamp": timestamp, "event": alarm})
        for alarm in sorted(self._alarms - machine.alarms):
            self.recorder.alarm(alarm, False, f"{alarm} normalizado", timestamp=timestamp)
        self._alarms = set(machine.alarms)
        if machine.compressor_command and not machine.compressor:
            self._mismatch_since = elapsed if self._mismatch_since is None else self._mismatch_since
            if elapsed - self._mismatch_since >= 5 and not self.first_deviation_recorded:
                self.recorder.deviation("compressor", "Compressor comandado sem resposta", {
                    "source": "SIMULADOR", "command": True, "feedback": False,
                }, timestamp)
                self.events.append({"timestamp": timestamp, "event": "COMPRESSOR_COMANDADO_SEM_RESPOSTA"})
                self.first_deviation_recorded = True
        else:
            self._mismatch_since = None

    def command_event(self, command: str, timestamp: str) -> None:
        self.recorder.marker(command, "Comando do cenário", timestamp=timestamp)
        self.events.append({"timestamp": timestamp, "event": command})
