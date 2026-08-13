from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class OperationMode(StrEnum):
    SIMULATOR = "SIMULADOR"
    REAL_READ_ONLY = "REAL / SOMENTE LEITURA"


class ConnectionState(StrEnum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONECTANDO"
    CONNECTED = "CONECTADO"
    DEGRADED = "DEGRADADO"
    ERROR = "ERRO"
    DISCONNECTED = "DESCONECTADO"


class DataQuality(StrEnum):
    VALID = "VÁLIDA"
    PROVISIONAL = "PROVISÓRIA"
    INVALID = "INVÁLIDA"
    STALE = "DESATUALIZADA"
    NO_DATA = "SEM DADOS"
    UNMAPPED = "NÃO MAPEADA"
    UNVALIDATED = "NÃO VALIDADA"


@dataclass
class BenchState:
    mode: OperationMode = OperationMode.SIMULATOR
    tcp_state: ConnectionState = ConnectionState.OFFLINE
    rs485_state: ConnectionState = ConnectionState.OFFLINE
    ipro_ip: str = "192.168.0.250"
    tcp_port: int = 502
    unit_id: int = 1
    latency_ms: float | None = None
    last_read: str | None = None
    tcp_errors: int = 0
    rs485_errors: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    @property
    def read_only(self) -> bool:
        return self.mode is OperationMode.REAL_READ_ONLY

    def set_mode(self, mode: OperationMode) -> None:
        self.mode = mode
        self.updated_at = datetime.now().astimezone().isoformat()
