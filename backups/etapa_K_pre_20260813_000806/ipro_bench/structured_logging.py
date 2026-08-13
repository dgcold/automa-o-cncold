from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class TechnicalError:
    module: str
    operation: str
    equipment: str = "NÃO APLICÁVEL"
    transport: str = "NÃO APLICÁVEL"
    endpoint: str = "NÃO APLICÁVEL"
    exception: str = ""
    classification: str = "ERRO TÉCNICO"
    timestamp: str = ""

    @classmethod
    def from_exception(cls, module: str, operation: str, error: Exception, **context) -> TechnicalError:
        return cls(module, operation, exception=f"{type(error).__name__}: {error}",
                   timestamp=datetime.now().astimezone().isoformat(), **context)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def log_technical_error(logger: logging.Logger, error: TechnicalError) -> None:
    logger.error(error.to_json())
