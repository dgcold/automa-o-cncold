from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IProSettings:
    host: str
    port: int
    unit_id: int
    timeout_seconds: float
    allowed_functions: tuple[int, ...]
    automatic_connection: bool


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baudrate: int
    bytesize: int
    parity: str
    stopbits: int
    automatic_start: bool


@dataclass(frozen=True)
class AnalysisSettings:
    history_page_limit: int
    export_limit: int
    timeline_limit: int


@dataclass(frozen=True)
class ApplicationSettings:
    name: str
    version: str
    default_mode: str
    ipro: IProSettings
    rs485: SerialSettings
    analysis: AnalysisSettings

    @classmethod
    def load(cls, path: str | Path) -> ApplicationSettings:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        application = payload["application"]
        ipro = dict(payload["ipro"])
        ipro["allowed_functions"] = tuple(ipro["allowed_functions"])
        settings = cls(
            application["name"], application["version"], application["default_mode"],
            IProSettings(**ipro), SerialSettings(**payload["rs485_simulator"]),
            AnalysisSettings(**payload["analysis"]),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.ipro.allowed_functions != (3, 4):
            raise ValueError("A configuração do iPro deve permitir exclusivamente FC03/FC04.")
        if self.ipro.automatic_connection:
            raise ValueError("Conexão automática com o iPro é proibida.")
        if self.rs485.automatic_start:
            raise ValueError("Inicialização automática do RS485 é proibida.")
        if min(self.analysis.history_page_limit, self.analysis.export_limit, self.analysis.timeline_limit) <= 0:
            raise ValueError("Limites de consulta devem ser positivos.")
