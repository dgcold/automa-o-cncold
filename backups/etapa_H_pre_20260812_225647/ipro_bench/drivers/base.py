from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..telemetry import TelemetrySample


class MapStatus(StrEnum):
    WAITING_OFFICIAL = "AGUARDANDO MAPA MODBUS OFICIAL"
    OFFICIAL_LOADED = "MAPA OFICIAL CARREGADO"


class DriverState(StrEnum):
    NOT_CONNECTED = "NÃO CONECTADO"
    CONNECTED = "CONECTADO"
    ERROR = "ERRO"


@dataclass(frozen=True)
class ControllerIdentity:
    id: str
    manufacturer: str
    model: str
    display_name: str
    protocol: str


@dataclass(frozen=True)
class DriverSnapshot:
    identity: ControllerIdentity
    state: DriverState
    map_status: MapStatus
    read_only: bool
    transport_active: bool
    variables: tuple[TelemetrySample, ...] = ()
    diagnostic: str = "SEM DADOS"


class ControllerDriver(ABC):
    """Contrato offline-first. Construção e seleção nunca ativam transporte."""

    def __init__(self, project_root: str | Path, official_map: str | Path) -> None:
        self.project_root = Path(project_root)
        self.official_map_path = Path(official_map)
        self._transport_active = False

    @property
    @abstractmethod
    def identity(self) -> ControllerIdentity:
        raise NotImplementedError

    @property
    def read_only(self) -> bool:
        return True

    @property
    def transport_active(self) -> bool:
        return self._transport_active

    def load_official_map(self) -> dict:
        with self.official_map_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("metadata", {}).get("status") != MapStatus.WAITING_OFFICIAL.value:
            raise ValueError("Somente mapas com estado oficial explícito são aceitos nesta etapa.")
        if payload.get("variables"):
            raise ValueError("O mapa oficial provisório deve permanecer vazio até o documento oficial.")
        return payload

    def snapshot(self) -> DriverSnapshot:
        payload = self.load_official_map()
        status = MapStatus(payload["metadata"]["status"])
        return DriverSnapshot(
            identity=self.identity,
            state=DriverState.NOT_CONNECTED,
            map_status=status,
            read_only=self.read_only,
            transport_active=False,
            variables=(),
            diagnostic="SEM MAPA · SEM DADOS · transporte inativo",
        )

    def normalized_variables(self) -> tuple[TelemetrySample, ...]:
        return self.snapshot().variables

    def communication_diagnostic(self) -> dict:
        snapshot = self.snapshot()
        return {
            "controller_id": snapshot.identity.id,
            "state": snapshot.state.value,
            "map_status": snapshot.map_status.value,
            "read_only": snapshot.read_only,
            "transport_active": snapshot.transport_active,
            "message": snapshot.diagnostic,
        }
