from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


class ReportExporter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _target(self, stem: str, suffix: str) -> Path:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        return self.output_dir / f"{stem}_{stamp}.{suffix}"

    def json(self, rows: Iterable[Mapping], stem: str = "relatorio") -> Path:
        target = self._target(stem, "json")
        target.write_text(json.dumps(list(rows), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        return target

    def csv(self, rows: Iterable[Mapping], stem: str = "relatorio") -> Path:
        data = [dict(row) for row in rows]
        target = self._target(stem, "csv")
        fields = list(dict.fromkeys(key for row in data for key in row))
        with target.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields or ["status"])
            writer.writeheader()
            if data:
                writer.writerows(data)
        return target

    def pdf(self, title: str, rows: Iterable[Mapping], stem: str = "relatorio") -> Path:
        """Create a dependency-free, text PDF suitable for offline bench reports."""
        data = [dict(row) for row in rows]
        lines = [title, datetime.now().astimezone().isoformat(), ""]
        for row in data:
            lines.append(" | ".join(f"{key}: {value}" for key, value in row.items()))
        if not data:
            lines.append("SEM DADOS")
        lines = lines[:48]
        commands = ["BT", "/F1 10 Tf", "48 790 Td"]
        for index, line in enumerate(lines):
            safe = str(line).encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if index:
                commands.append("0 -15 Td")
            commands.append(f"({safe[:110]}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for number, obj in enumerate(objects, 1):
            offsets.append(len(document))
            document.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = len(document)
        document.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            document.extend(f"{offset:010d} 00000 n \n".encode())
        document.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        target = self._target(stem, "pdf")
        target.write_bytes(document)
        return target
