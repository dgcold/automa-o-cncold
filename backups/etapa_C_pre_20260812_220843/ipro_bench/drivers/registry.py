from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .base import ControllerDriver
from .fullgauge_vx1050e.driver import FullGaugeVX1050EDriver
from .ipro.driver import IProDriver


class ControllerRegistry:
    def __init__(self, drivers: Iterable[ControllerDriver] = ()) -> None:
        self._drivers: dict[str, ControllerDriver] = {}
        for driver in drivers:
            self.register(driver)

    def register(self, driver: ControllerDriver) -> None:
        controller_id = driver.identity.id
        if controller_id in self._drivers:
            raise ValueError(f"Controlador duplicado: {controller_id}")
        self._drivers[controller_id] = driver

    def get(self, controller_id: str) -> ControllerDriver:
        try:
            return self._drivers[controller_id]
        except KeyError as error:
            raise KeyError(f"Controlador desconhecido: {controller_id}") from error

    def all(self) -> tuple[ControllerDriver, ...]:
        return tuple(self._drivers.values())


def build_default_registry(project_root: str | Path) -> ControllerRegistry:
    root = Path(project_root)
    return ControllerRegistry((IProDriver(root), FullGaugeVX1050EDriver(root)))
