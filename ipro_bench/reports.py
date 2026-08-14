from __future__ import annotations

import csv
import json
import textwrap
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path


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

    def diagnostic_pdf(self, diagnostic, stem: str = "diagnostico") -> Path:
        """Place the interpreted diagnosis before the complete raw evidence."""
        from .technician_diagnostics import display_value
        first=diagnostic.first_deviation
        sections=[
            ("RESUMO DO DIAGNÓSTICO",[f"EQUIPAMENTO: {diagnostic.equipment}",f"SESSÃO: {diagnostic.session_id}",f"DATA: {diagnostic.date}",f"DURAÇÃO: {diagnostic.duration}",f"STATUS: {diagnostic.machine_status}",f"FALHA / ANOMALIA: {diagnostic.anomaly}",f"CONFIANÇA: {'NÃO DETERMINADA' if diagnostic.confidence is None else f'{diagnostic.confidence:.0%}'}"]),
            ("PRIMEIRO DESVIO",["NÃO IDENTIFICADO"] if first is None else [f"HORÁRIO: {first.timestamp}",f"VARIÁVEL: {first.variable}",f"VALOR ANTERIOR: {display_value(first.previous_value)}",f"VALOR ATUAL: {display_value(first.current_value)}",f"DIFERENÇA: {display_value(first.difference)}",f"ESPERADO: {first.expected}",f"OBSERVADO: {first.observed}",f"SEVERIDADE: {first.severity}",f"EVIDÊNCIAS: {', '.join(map(str,first.evidence_ids)) or 'SEM DADOS'}"]),
            ("ANÁLISE - O QUE ACONTECEU",[diagnostic.what_happened]),("O QUE FOI OBSERVADO",list(diagnostic.observations)),
            ("EVIDÊNCIAS",[", ".join(map(str,diagnostic.evidence_ids)) or "SEM DADOS"]),("HIPÓTESES",list(diagnostic.hypotheses)),
            ("IMPACTO",[diagnostic.impact]),("VERIFICAÇÕES RECOMENDADAS",list(diagnostic.recommended_checks)),
            ("CONFIRMAÇÃO DO TÉCNICO",[diagnostic.technician_confirmation]),
            ("REGISTROS BRUTOS / EVIDÊNCIAS COMPLETAS",[json.dumps(r,ensure_ascii=False,default=str) for r in diagnostic.raw_records] or ["SEM DADOS"])]
        lines=["CNCold Industrial Diagnostics",datetime.now().astimezone().isoformat(),""]
        for heading,content in sections:
            lines.extend((heading,"="*min(72,len(heading))))
            for item in content:lines.extend(textwrap.wrap(str(item),width=92) or [""])
            lines.append("")
        return self._reportlab_diagnostic_pdf(sections, diagnostic, stem)

    def _reportlab_diagnostic_pdf(self, sections, diagnostic, stem: str) -> Path:
        from html import escape
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

        target=self._target(stem,"pdf");font_name="Helvetica";bold_name="Helvetica-Bold"
        regular=Path("C:/Windows/Fonts/arial.ttf");bold=Path("C:/Windows/Fonts/arialbd.ttf")
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("CNCold",str(regular)));pdfmetrics.registerFont(TTFont("CNCold-Bold",str(bold)))
            font_name,bold_name="CNCold","CNCold-Bold"
        styles=getSampleStyleSheet();body=ParagraphStyle("CNBody",parent=styles["BodyText"],fontName=font_name,fontSize=9.2,leading=13,textColor=colors.HexColor("#243447"),spaceAfter=3)
        heading=ParagraphStyle("CNHeading",parent=body,fontName=bold_name,fontSize=12,leading=15,textColor=colors.HexColor("#0F5E91"),spaceBefore=8,spaceAfter=6)
        title=ParagraphStyle("CNTitle",parent=heading,fontSize=19,leading=23,alignment=TA_CENTER,textColor=colors.HexColor("#123A59"),spaceAfter=4)
        subtitle=ParagraphStyle("CNSubtitle",parent=body,alignment=TA_CENTER,textColor=colors.HexColor("#60788C"),spaceAfter=14)
        raw=ParagraphStyle("CNRaw",parent=body,fontName=font_name,fontSize=7.2,leading=10,textColor=colors.HexColor("#465A6B"),leftIndent=4*mm)
        def footer(canvas,doc):
            canvas.saveState();canvas.setFont(font_name,8);canvas.setFillColor(colors.HexColor("#60788C"));canvas.drawString(18*mm,10*mm,"CNCold Industrial Diagnostics - Evidência rastreável");canvas.drawRightString(192*mm,10*mm,f"Página {doc.page}");canvas.restoreState()
        document=SimpleDocTemplate(str(target),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=17*mm,
            title="Diagnóstico da ocorrência",author="CNCold Industrial Diagnostics")
        story=[Paragraph("DIAGNÓSTICO DA OCORRÊNCIA",title),Paragraph(f"Sessão {escape(diagnostic.session_id)} - aguardando confirmação do técnico",subtitle)]
        for section_name,content in sections:
            block=[Paragraph(escape(section_name),heading)]
            for item in content:
                text=escape(str(item)).replace("\n","<br/>")
                block.append(Paragraph(text,raw if section_name.startswith("REGISTROS BRUTOS") else body))
            block.append(Spacer(1,2*mm));story.append(KeepTogether(block) if len(block)<=8 else block[0])
            if len(block)>8:story.extend(block[1:])
        document.build(story,onFirstPage=footer,onLaterPages=footer)
        return target

    def _text_pdf_pages(self,lines:list[str],stem:str)->Path:
        pages=[lines[i:i+48] for i in range(0,len(lines),48)] or [["SEM DADOS"]];objects=[b"<< /Type /Catalog /Pages 2 0 R >>"]
        page_ids=[];streams=[];next_id=3
        for page in pages:
            page_ids.append(next_id);stream_id=next_id+1;next_id+=2;commands=["BT","/F1 9 Tf","42 800 Td"]
            for index,line in enumerate(page):
                safe=str(line).encode("latin-1","replace").decode("latin-1").replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
                if index:commands.append("0 -15 Td")
                commands.append(f"({safe[:105]}) Tj")
            commands.append("ET");streams.append((stream_id,"\n".join(commands).encode("latin-1")))
        font_id=next_id;objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {len(page_ids)} >>".encode())
        for page_id,(stream_id,stream) in zip(page_ids,streams):
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode());objects.append(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");document=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n");offsets=[0]
        for number,obj in enumerate(objects,1):offsets.append(len(document));document.extend(f"{number} 0 obj\n".encode()+obj+b"\nendobj\n")
        xref=len(document);document.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:document.extend(f"{offset:010d} 00000 n \n".encode())
        document.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode());target=self._target(stem,"pdf");target.write_bytes(document);return target
