from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .core import DataQuality
from .history_store import PersistentHistory
from .telemetry import ChannelDefinition, TelemetrySample, unavailable_sample

ELECTRICAL_CHANNELS = (
    ChannelDefinition("current_total", "Corrente total da máquina", "MEDIÇÃO ELÉTRICA", "A"),
    ChannelDefinition("current_compressor", "Corrente do compressor", "MEDIÇÃO ELÉTRICA", "A"),
    ChannelDefinition("current_l1", "Corrente L1", "MEDIÇÃO ELÉTRICA", "A"),
    ChannelDefinition("current_l2", "Corrente L2", "MEDIÇÃO ELÉTRICA", "A"),
    ChannelDefinition("current_l3", "Corrente L3", "MEDIÇÃO ELÉTRICA", "A"),
)


@dataclass(frozen=True)
class ElectricalSnapshot:
    connected: bool
    source: str
    samples: tuple[TelemetrySample, ...]


class ElectricalMeasurementService:
    """Hardware-neutral boundary prepared for a future EM210 driver."""

    def __init__(self, history: PersistentHistory | None = None) -> None:
        self.history = history
        self.connected = False
        self.source = "EM210 · NÃO CONECTADO"
        self._latest = {item.id: unavailable_sample(item) for item in ELECTRICAL_CHANNELS}

    def snapshot(self) -> ElectricalSnapshot:
        return ElectricalSnapshot(self.connected, self.source, tuple(self._latest.values()))

    def disconnect(self) -> ElectricalSnapshot:
        self.connected = False
        self.source = "EM210 · NÃO CONECTADO"
        self._latest = {item.id: unavailable_sample(item) for item in ELECTRICAL_CHANNELS}
        return self.snapshot()

    def ingest(self, values: Mapping[str, float | int | None], source: str = "EM210") -> ElectricalSnapshot:
        """Accept values only from an external driver; this service never opens hardware."""
        self.connected = True
        self.source = source
        timestamp = datetime.now().astimezone().isoformat()
        updated: dict[str, TelemetrySample] = {}
        for channel in ELECTRICAL_CHANNELS:
            value = values.get(channel.id)
            quality = DataQuality.VALID if value is not None else DataQuality.NO_DATA
            sample = TelemetrySample(
                channel.id, channel.name, channel.group, channel.unit, value,
                quality, source, True, timestamp,
            )
            updated[channel.id] = sample
            if self.history is not None:
                self.history.append(sample)
        self._latest = updated
        return self.snapshot()

    def statistics(self, channel_id: str) -> dict[str, float | int | None]:
        if self.history is None:
            return {"count": 0, "average": None, "minimum": None, "maximum": None}
        return self.history.statistics(channel_id)
