from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


EVIDENCE_CATEGORIES = (
    "tcp", "rs485", "testes", "sensores", "io", "alarmes", "cenarios",
    "medicao_eletrica", "historico", "relatorios",
)


class EvidenceStore:
    """Persistência append-only em JSONL; evidência existente nunca é removida."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        for category in EVIDENCE_CATEGORIES:
            (self.root / category).mkdir(parents=True, exist_ok=True)

    def append(self, category: str, event: dict[str, Any], session: str = "bench") -> Path:
        if category not in EVIDENCE_CATEGORIES:
            raise ValueError(f"Categoria de evidência inválida: {category}")
        timestamp = datetime.now().astimezone().isoformat()
        record = {"timestamp": timestamp, **event}
        target = self.root / category / f"{session}.jsonl"
        with self._lock, target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return target

    def count(self, category: str | None = None) -> int:
        categories = (category,) if category else EVIDENCE_CATEGORIES
        total = 0
        for name in categories:
            for path in (self.root / name).glob("*.jsonl"):
                with path.open("r", encoding="utf-8") as stream:
                    total += sum(1 for line in stream if line.strip())
        return total
