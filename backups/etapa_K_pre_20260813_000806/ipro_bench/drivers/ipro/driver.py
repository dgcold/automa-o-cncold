from __future__ import annotations

from pathlib import Path

from ..base import ControllerDriver, ControllerIdentity


class IProDriver(ControllerDriver):
    ALLOWED_FUNCTIONS = frozenset((3, 4))

    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root)
        super().__init__(root, root / "config" / "controllers" / "ipro" / "official_map.json")

    @property
    def identity(self) -> ControllerIdentity:
        return ControllerIdentity("ipro", "Copeland / Emerson", "iPro IPG215D", "Copeland iPro", "Modbus TCP")

    def validate_function(self, function: int) -> None:
        if function not in self.ALLOWED_FUNCTIONS:
            raise PermissionError("iPro real permite exclusivamente FC03/FC04 em somente leitura.")

    @property
    def candidate_map_path(self) -> Path:
        return self.project_root / "config" / "modbus_map.json"
