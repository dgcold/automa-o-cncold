from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...telemetry import TelemetrySample


class EM210Role(StrEnum):
    MACHINE_TOTAL = "TOTAL DA MÁQUINA"
    COMPRESSOR = "COMPRESSOR"


@dataclass(frozen=True)
class EM210Identity:
    id: str
    manufacturer: str
    model: str
    role: EM210Role


class EM210Driver:
    """Fronteira offline preparada para mapa oficial, sem presumir transporte."""

    def __init__(self, project_root: str | Path, role: EM210Role) -> None:
        self.project_root = Path(project_root)
        self.role = role
        suffix = "total" if role is EM210Role.MACHINE_TOTAL else "compressor"
        self.identity = EM210Identity(f"em210_{suffix}", "Carlo Gavazzi", "EM210", role)
        self.config_path = self.project_root / "config" / "controllers" / f"em210_{suffix}" / "driver.json"
        self.official_map_path = self.project_root / "config" / "controllers" / f"em210_{suffix}" / "official_map.json"
        self._transport_active = False

    @property
    def transport_active(self) -> bool:
        return self._transport_active

    @property
    def read_only(self) -> bool:
        return True

    def official_map(self) -> dict:
        payload = json.loads(self.official_map_path.read_text(encoding="utf-8"))
        if payload.get("variables"):
            raise ValueError("Mapa EM210 provisório deve permanecer vazio até o documento oficial.")
        return payload

    def normalized_variables(self) -> tuple[TelemetrySample, ...]:
        return ()

    def diagnostic(self) -> dict:
        return {
            "id": self.identity.id,
            "role": self.role.value,
            "state": "NÃO CONECTADO",
            "data": "SEM DADOS",
            "map": "AGUARDANDO DRIVER/MAPA OFICIAL",
            "transport_active": False,
            "read_only": True,
        }


def build_em210_drivers(project_root: str | Path) -> tuple[EM210Driver, EM210Driver]:
    return (
        EM210Driver(project_root, EM210Role.MACHINE_TOTAL),
        EM210Driver(project_root, EM210Role.COMPRESSOR),
    )
