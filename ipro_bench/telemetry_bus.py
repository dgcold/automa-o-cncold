from __future__ import annotations

from collections.abc import Iterable

from .field_diagnostics import BlackBoxRecorder
from .history_store import PersistentHistory
from .telemetry import TelemetrySample


class TelemetryBus:
    """Single offline path coordinating normalized history and black-box writes."""

    def __init__(self, history: PersistentHistory, blackbox: BlackBoxRecorder) -> None:
        self.history = history
        self.blackbox = blackbox
        self.published = 0

    def publish(self, samples: Iterable[TelemetrySample]) -> int:
        batch = tuple(samples)
        if any(sample.source != "SIMULADOR" for sample in batch):
            raise ValueError("O barramento de simulação aceita apenas origem SIMULADOR.")
        self.history.append_many(batch)
        written = self.blackbox.ingest(batch)
        self.published += len(batch)
        return written
