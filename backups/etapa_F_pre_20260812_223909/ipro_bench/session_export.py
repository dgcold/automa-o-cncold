from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from .field_diagnostics import BlackBoxStore, TimelineAnalyzer
from .reports import ReportExporter


class DiagnosticSessionExporter:
    def __init__(self, store: BlackBoxStore, output_dir: str | Path) -> None:
        self.store = store
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_bundle(self, session_id: str) -> Path:
        session = self.store.get_session(session_id)
        records = self.store.query(session_id)
        target = self.output_dir / f"sessao_{session_id}.zip"
        session_json = json.dumps({"session": asdict(session), "timeline": records}, ensure_ascii=False, indent=2, default=str)
        csv_path = self.output_dir / f".{session_id}.csv"
        fields = list(records[0]) if records else ["status"]
        with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in records:
                writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("session.json", session_json)
            bundle.write(csv_path, "timeline.csv")
        csv_path.unlink()
        return target

    def report(self, session_id: str) -> Path:
        summary = TimelineAnalyzer(self.store).summary(session_id)
        first = summary["first_deviation"]
        rows = [{
            "sessao": session_id,
            "registros": summary["records"],
            "primeiro_desvio": first["message"] if first else "NÃO IDENTIFICADO",
            "retornou_ao_normal": "SIM" if summary["recovered"] else "NÃO DETERMINADO",
            "evidencias": len(summary["evidence_ids"]),
        }]
        return ReportExporter(self.output_dir).pdf("Relatório de Diagnóstico de Campo", rows, f"sessao_{session_id}")
