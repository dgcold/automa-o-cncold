from types import SimpleNamespace

from ipro_bench.reports import ReportExporter
from ipro_bench.technician_diagnostics import (
    ConfirmationDecision, TechnicianConfirmationRepository,
    TechnicianDiagnosticEngine, display_value, technician_label,
)


def row(identifier, variable, value, seconds=0, **extra):
    return {"id":identifier,"kind":"AMOSTRA","variable_id":variable,"value":value,"previous_value":None,
            "quality":"VÁLIDA","timestamp":f"2026-08-13T00:00:{seconds:02d}-03:00","timestamp_ns":seconds*1_000_000_000,
            "name":"","message":"","severity":"","evidence":{},**extra}


def test_names_are_translated_and_unknown_names_remain_readable():
    assert technician_label("current_l3")=="CORRENTE FASE L3"
    assert technician_label("temperature_chamber")=="TEMPERATURA DA CÂMARA"
    assert technician_label("custom_signal")=="CUSTOM SIGNAL"
    assert display_value(True)=="LIGADO" and display_value(False)=="DESLIGADO" and display_value(None)=="SEM DADOS"


def test_phase_imbalance_is_interpreted_with_evidence_and_checks():
    result=TechnicianDiagnosticEngine().analyze("S1",[row(1,"current_l1",10),row(2,"current_l2",10),row(3,"current_l3",5)])
    assert result.anomaly=="DESEQUILÍBRIO DE FASES"
    assert "FASE MAIS DESVIADA: L3" in result.observations
    assert result.evidence_ids==(1,2,3) and 0 < result.confidence < 1
    assert "Possível" in result.hypotheses[0]


def test_compressor_command_is_not_treated_as_physical_confirmation():
    result=TechnicianDiagnosticEngine().analyze("S2",[row(7,"compressor_command",True),row(8,"compressor",False)])
    assert result.anomaly=="COMANDO SEM CONFIRMAÇÃO DO COMPRESSOR"
    assert result.observations==("COMANDO DO COMPRESSOR: LIGADO","ESTADO DO COMPRESSOR: DESLIGADO")
    assert len(result.hypotheses)>=4 and result.evidence_ids==(7,8)


def test_first_explicit_deviation_is_prominent_and_traceable():
    deviation=row(11,"pressure_suction",2.1,4,kind="DESVIO",previous_value=3.0,message="Pressão abaixo do esperado",evidence={"expected":"3 bar","severity":"ANORMAL"})
    result=TechnicianDiagnosticEngine().analyze("S3",[deviation])
    assert result.first_deviation.variable=="PRESSÃO DE SUCÇÃO"
    assert result.first_deviation.difference==-0.9
    assert result.first_deviation.evidence_ids==(11,)


def test_missing_data_does_not_mean_normal():
    result=TechnicianDiagnosticEngine().analyze("S4",[])
    assert result.anomaly=="DADOS INSUFICIENTES" and result.confidence is None
    assert result.hypotheses==("NÃO DETERMINADO",)


def test_technician_confirmation_records_identity_decision_time_and_note(tmp_path):
    repository=TechnicianConfirmationRepository(tmp_path/"confirmations.sqlite3")
    saved=repository.record("S1","Ana","Desequilíbrio",ConfirmationDecision.REJECTED,"Medição física normal")
    assert saved["technician"]=="Ana" and saved["timestamp"] and saved["observation"]
    assert repository.latest("S1")["decision"]=="HIPÓTESE REJEITADA"


def test_confirmation_requires_technician(tmp_path):
    repository=TechnicianConfirmationRepository(tmp_path/"confirmations.sqlite3")
    try: repository.record("S1","","X",ConfirmationDecision.INCONCLUSIVE)
    except ValueError: pass
    else: raise AssertionError("Confirmação sem técnico foi aceita")


def test_defrost_presentation_reports_phases_and_missing_data():
    phase=SimpleNamespace(phase=SimpleNamespace(value="DEGELO"),duration_seconds=60)
    cycle=SimpleNamespace(phases=(phase,),temperatures=(),status=SimpleNamespace(value="INCOMPLETO"),quality_score=.9,
        first_deviation=None,session_id="D1",duration_seconds=60,evidence_ids=(20,21))
    result=TechnicianDiagnosticEngine().analyze_defrost(cycle)
    assert result.anomaly=="DEGELO INCOMPLETO"
    assert "DEGELO: 60.0 s" in result.observations and "GOTEJAMENTO: SEM DADOS" in result.observations


def test_layered_pdf_puts_summary_before_complete_raw_records(tmp_path):
    from pypdf import PdfReader
    diagnostic=TechnicianDiagnosticEngine().analyze("PDF1",[row(1,"current_l1",10),row(2,"current_l2",10),row(3,"current_l3",5)])
    target=ReportExporter(tmp_path).diagnostic_pdf(diagnostic)
    payload=target.read_bytes()
    text="\n".join(page.extract_text() or "" for page in PdfReader(target).pages)
    assert payload.startswith(b"%PDF-1.4") and "RESUMO DO DIAGNÓSTICO" in text
    assert text.find("PRIMEIRO DESVIO") < text.find("REGISTROS BRUTOS")
