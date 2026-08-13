from __future__ import annotations

from pathlib import Path

from ..base import ControllerDriver, ControllerIdentity


class FullGaugeVX1050EDriver(ControllerDriver):
    """Esqueleto offline; não presume transporte, função ou registradores."""

    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root)
        super().__init__(root, root / "config" / "controllers" / "fullgauge_vx1050e" / "official_map.json")

    @property
    def identity(self) -> ControllerIdentity:
        return ControllerIdentity("fullgauge_vx1050e", "Full Gauge Controls", "VX-1050E", "Full Gauge VX-1050E", "AGUARDANDO DEFINIÇÃO OFICIAL")
