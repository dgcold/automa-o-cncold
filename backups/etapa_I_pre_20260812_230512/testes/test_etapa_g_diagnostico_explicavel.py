import hashlib

import pytest

from ipro_bench.explainable_diagnostics import (
    ConclusionState, DiagnosticRepository, ExplainableDiagnosticEngine, RuleCatalog, TechnicalRule,
)
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore, TimelineKind, TimelineRecord


def evidence_session(store):
    recorder=BlackBoxRecorder(store);session=recorder.start("ipro","Diagnóstico offline")
    ids=[]
    for index,(kind,name) in enumerate(((TimelineKind.DEVIATION,"pressao_caiu"),(TimelineKind.STATE_CHANGE,"compressor_off"),(TimelineKind.SAMPLE,"temperatura_estavel"))):
        ids.append(store.append(session.id,TimelineRecord(kind,f"2031-01-01T00:00:0{index}+00:00",2_000_000_000_000_000_000+index,name,name,index,quality="VÁLIDA",evidence={"source":"offline"})))
    recorder.stop();return session,ids


def rule(**overrides):
    data=dict(id="R-001",version="1",description="Regra controlada",context="ALARME",
        hypothesis="Hipótese técnica controlada",favorable_facts=("pressao_caiu","compressor_off"),
        contrary_facts=("temperatura_estavel",),required_confirmation_facts=("teste_fisico_confirmou",),
        missing_information=(),recommended_test="Executar teste autorizado")
    data.update(overrides);return TechnicalRule(**data)


@pytest.fixture
def setup(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3");repo=DiagnosticRepository(tmp_path/"diag.sqlite3")
    return store,repo


def test_hypothesis_creation_with_traceability(setup):
    store,repo=setup;session,ids=evidence_session(store);engine=ExplainableDiagnosticEngine(store,repo,[rule()])
    result=engine.evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME",event_id=ids[1],first_deviation_id=ids[0])[0]
    assert result.state is ConclusionState.HYPOTHESIS
    assert result.evidence_ids==(ids[0],) and result.first_deviation_id==ids[0]
    assert result.causality=="NÃO ESTABELECIDA"


def test_favorable_and_contrary_evidence_adjust_confidence(setup):
    store,repo=setup;session,ids=evidence_session(store);engine=ExplainableDiagnosticEngine(store,repo,[rule()])
    favorable=engine.evaluate(session.id,{"pressao_caiu":[ids[0]],"compressor_off":[ids[1]]},context="ALARME")[0]
    contrary=engine.evaluate(session.id,{"pressao_caiu":[ids[0]],"compressor_off":[ids[1]],"temperatura_estavel":[ids[2]]},context="ALARME")[0]
    assert len(favorable.favorable)==2 and len(contrary.contrary)==1
    assert favorable.confidence>contrary.confidence


def test_confidence_is_never_automatic_confirmation(setup):
    store,repo=setup;session,ids=evidence_session(store);strong=rule(contrary_facts=(),required_confirmation_facts=())
    result=ExplainableDiagnosticEngine(store,repo,[strong]).evaluate(session.id,{"pressao_caiu":[ids[0]],"compressor_off":[ids[1]]},context="ALARME")[0]
    assert result.confidence<=.95 and result.state is ConclusionState.HYPOTHESIS


def test_competing_hypotheses_are_ranked_not_selected(setup):
    store,repo=setup;session,ids=evidence_session(store)
    rules=[rule(id="R1",hypothesis="H1"),rule(id="R2",hypothesis="H2",favorable_facts=("pressao_caiu",))]
    engine=ExplainableDiagnosticEngine(store,repo,rules);items=engine.evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")
    comparison=engine.competing(items)
    assert len(comparison)==2 and all(row["causality"]=="NÃO ESTABELECIDA" for row in comparison)


def test_discard_hypothesis_and_audit(setup):
    store,repo=setup;session,ids=evidence_session(store);item=ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")[0]
    discarded=repo.transition(item.id,ConclusionState.DISCARDED,"engenheiro","Evidência contrária")
    assert discarded.state is ConclusionState.DISCARDED
    assert [row["action"] for row in repo.audit(item.id)]==["CRIADA","HIPÓTESE DESCARTADA"]


def test_no_evidence_creates_no_hypothesis(setup):
    store,repo=setup;session,_=evidence_session(store)
    assert ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{},context="ALARME")==[]


def test_wrong_context_creates_no_generic_text(setup):
    store,repo=setup;session,ids=evidence_session(store)
    assert ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="DEGELO")==[]


def test_missing_confirmation_and_recommended_test(setup):
    store,repo=setup;session,ids=evidence_session(store);item=ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")[0]
    assert item.missing_confirmation==("teste_fisico_confirmou",)
    assert item.recommended_test=="Executar teste autorizado"


def test_cannot_promote_with_missing_confirmation(setup):
    store,repo=setup;session,ids=evidence_session(store);item=ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")[0]
    with pytest.raises(ValueError,match="pendentes"):
        repo.transition(item.id,ConclusionState.SUFFICIENT_EVIDENCE,"engenheiro")


def test_confirmation_requires_explicit_evidence(setup):
    store,repo=setup;session,ids=evidence_session(store);clean=rule(required_confirmation_facts=())
    item=ExplainableDiagnosticEngine(store,repo,[clean]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")[0]
    sufficient=repo.transition(item.id,ConclusionState.SUFFICIENT_EVIDENCE,"engenheiro")
    with pytest.raises(ValueError,match="evidência"):
        repo.transition(sufficient.id,ConclusionState.CONFIRMED,"engenheiro")
    confirmed=repo.transition(sufficient.id,ConclusionState.CONFIRMED,"engenheiro",confirmation_evidence=[ids[2]])
    assert confirmed.state is ConclusionState.CONFIRMED and confirmed.causality=="CONFIRMADA MANUALMENTE"


def test_invalid_evidence_from_another_source_is_rejected(setup):
    store,repo=setup;session,_=evidence_session(store)
    with pytest.raises(ValueError,match="não pertence"):
        ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[99999]},context="ALARME")


def test_preserves_original_evidence_store(setup):
    store,repo=setup;session,ids=evidence_session(store);before=hashlib.sha256(store.path.read_bytes()).hexdigest()
    ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before


def test_default_catalog_has_no_unvalidated_rules(project_dir):
    catalog=RuleCatalog(project_dir/"config"/"diagnostic_rules.json")
    assert catalog.load()==()


def test_repository_history_persists(setup):
    store,repo=setup;session,ids=evidence_session(store);item=ExplainableDiagnosticEngine(store,repo,[rule()]).evaluate(session.id,{"pressao_caiu":[ids[0]]},context="ALARME")[0]
    assert repo.get(item.id).description==item.description and repo.list()[0].id==item.id


@pytest.fixture
def project_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
