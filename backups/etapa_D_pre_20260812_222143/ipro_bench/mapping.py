from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "id", "name", "group", "w1_index", "unit_id", "function", "address",
    "quantity", "offset", "data_type", "signed", "scale", "unit", "status",
    "origin", "evidence", "confidence", "notes",
}


@dataclass(frozen=True)
class MapValidation:
    valid: bool
    errors: tuple[str, ...]
    sha256: str
    variable_count: int


class ModbusMapRepository:
    def __init__(self, active_path: str | Path, history_dir: str | Path) -> None:
        self.active_path = Path(active_path)
        self.history_dir = Path(history_dir)

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def load(self) -> dict[str, Any]:
        with self.active_path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def validate_payload(self, payload: dict[str, Any]) -> MapValidation:
        errors: list[str] = []
        if not isinstance(payload.get("metadata"), dict):
            errors.append("metadata ausente ou inválido")
        variables = payload.get("variables")
        if not isinstance(variables, list):
            errors.append("variables deve ser uma lista")
            variables = []
        ids: set[str] = set()
        for index, item in enumerate(variables):
            if not isinstance(item, dict):
                errors.append(f"variables[{index}] não é objeto")
                continue
            missing = REQUIRED_FIELDS - item.keys()
            if missing:
                errors.append(f"variables[{index}] campos ausentes: {', '.join(sorted(missing))}")
            variable_id = str(item.get("id", ""))
            if variable_id in ids:
                errors.append(f"id duplicado: {variable_id}")
            ids.add(variable_id)
            function = item.get("function")
            if function not in (None, 3, 4):
                errors.append(f"{variable_id}: somente FC03/FC04 são aceitas")
        digest = hashlib.sha256(self._canonical(payload)).hexdigest()
        return MapValidation(not errors, tuple(errors), digest, len(variables))

    def validate_file(self, path: str | Path) -> tuple[dict[str, Any], MapValidation]:
        with Path(path).open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        return payload, self.validate_payload(payload)

    def differences(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        current = {v["id"]: v for v in self.load().get("variables", [])}
        proposed = {v["id"]: v for v in candidate.get("variables", [])}
        rows = []
        for variable_id in sorted(current.keys() | proposed.keys()):
            if current.get(variable_id) != proposed.get(variable_id):
                rows.append({"id": variable_id, "current": current.get(variable_id), "proposed": proposed.get(variable_id)})
        return rows

    def stage(self, source: str | Path) -> Path:
        payload, validation = self.validate_file(source)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        self.history_dir.mkdir(parents=True, exist_ok=True)
        version = str(payload["metadata"].get("version", "sem_versao")).replace("/", "-")
        target = self.history_dir / f"mapa_{version}_{validation.sha256[:12]}_PENDENTE.json"
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return target
