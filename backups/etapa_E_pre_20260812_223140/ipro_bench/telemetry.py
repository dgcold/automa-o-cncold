from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .core import DataQuality


@dataclass(frozen=True)
class TelemetrySample:
    """A normalized observation flowing through the bench architecture."""

    channel_id: str
    name: str
    group: str
    unit: str
    value: float | int | bool | None = None
    quality: DataQuality = DataQuality.NO_DATA
    source: str = "NÃO CONECTADO"
    connected: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.connected and self.value is not None:
            raise ValueError("Uma fonte não conectada não pode publicar valor.")
        if self.quality is DataQuality.NO_DATA and self.value is not None:
            raise ValueError("SEM DADOS não pode conter valor.")

    @property
    def display_value(self) -> str:
        return "SEM DADOS" if self.value is None else str(self.value)

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["quality"] = self.quality.value
        return record


@dataclass(frozen=True)
class ChannelDefinition:
    id: str
    name: str
    group: str
    unit: str
    direction: str = "ENTRADA"
    source: str = "AGUARDANDO MAPA OFICIAL"
    writable: bool = False


def unavailable_sample(channel: ChannelDefinition) -> TelemetrySample:
    return TelemetrySample(
        channel_id=channel.id,
        name=channel.name,
        group=channel.group,
        unit=channel.unit,
        quality=DataQuality.NO_DATA,
        source=channel.source,
        connected=False,
    )
