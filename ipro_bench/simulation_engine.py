from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class SimulationStatus(StrEnum):
    READY = "PRONTO"
    RUNNING = "EM EXECUÇÃO"
    PAUSED = "PAUSADO"
    STOPPED = "PARADO"
    FINISHED = "FINALIZADO"


@dataclass
class SimulationEngine:
    seed: int = 1
    speed: int = 1
    start_time: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        if self.speed not in (1, 10, 100):
            raise ValueError("Velocidade permitida: 1x, 10x ou 100x.")
        self.execution_id = f"EXE-{uuid.uuid4().hex[:12].upper()}"
        self.elapsed = 0.0
        self.status = SimulationStatus.READY

    @property
    def timestamp(self) -> str:
        return (self.start_time + timedelta(seconds=self.elapsed)).isoformat()

    def start(self) -> None:
        if self.status not in (SimulationStatus.READY, SimulationStatus.PAUSED):
            raise ValueError("Execução não está disponível para início.")
        self.status = SimulationStatus.RUNNING

    def pause(self) -> None:
        if self.status is SimulationStatus.RUNNING:
            self.status = SimulationStatus.PAUSED

    def resume(self) -> None:
        if self.status is not SimulationStatus.PAUSED:
            raise ValueError("Execução não está pausada.")
        self.status = SimulationStatus.RUNNING

    def stop(self) -> None:
        self.status = SimulationStatus.STOPPED

    def step(self, seconds: float, callback: Callable[[float, str], None]) -> None:
        if self.status is not SimulationStatus.RUNNING:
            raise RuntimeError("Execução não está ativa.")
        dt = max(0.0, float(seconds))
        self.elapsed += dt
        callback(dt, self.timestamp)

    def run_headless(self, duration: float, callback: Callable[[float, str], None], step_seconds: float = 1.0) -> None:
        if self.status is SimulationStatus.READY:
            self.start()
        while self.status is SimulationStatus.RUNNING and self.elapsed < duration:
            self.step(min(step_seconds, duration - self.elapsed), callback)
        if self.status is SimulationStatus.RUNNING:
            self.status = SimulationStatus.FINISHED
