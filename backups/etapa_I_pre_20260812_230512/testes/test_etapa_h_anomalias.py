import hashlib

import pytest

from ipro_bench.anomaly_analysis import AlgorithmVersion, AnalysisState, AnomalyClass, AnomalyEngine, AnomalyRepository
from ipro_bench.baseline import BaselineRepository, BaselineService, BaselineStatus, OperationalContext
from ipro_bench.core import DataQuality
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore
from ipro_bench.telemetry import TelemetrySample


def session(store,values,quality=DataQuality.VALID,variable="temp"):
    recorder=BlackBoxRecorder(store);item=recorder.start("ipro","offline")
    for index,value in enumerate(values):recorder.ingest([TelemetrySample(variable,variable,"PROCESSO","u",value,quality,"OFFLINE",True,f"2032-01-01T00:00:0{index}+00:00")])
    recorder.stop();return item


@pytest.fixture
def setup(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3");baselines=BaselineRepository(tmp_path/"base.sqlite3");repo=AnomalyRepository(tmp_path/"ai.sqlite3")
    service=BaselineService(store,baselines);reference=session(store,[9,10,11,10]);base=service.create_candidate("ipro","M1",OperationalContext.NORMAL,[reference.id]);baselines.transition(base.id,BaselineStatus.VALIDATED,"eng")
    return store,baselines,repo,base,AnomalyEngine(store,baselines,repo)


def test_known_anomaly(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[20,21,22,23]).id,base.id)
    assert result.classification is AnomalyClass.ANOMALOUS and result.anomaly_score>0
    assert result.factors[0].first_anomalous_timestamp


def test_normal_behavior(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[9.5,10,10.5]).id,base.id)
    assert result.classification is AnomalyClass.NORMAL


def test_absence_of_anomaly_has_zero_or_low_score(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[10,10,10]).id,base.id)
    assert result.anomaly_score<50 and not result.abstention_reason


def test_insufficient_data_abstains(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[20]).id,base.id)
    assert result.state is AnalysisState.ABSTAINED and result.abstention_reason=="DADOS INSUFICIENTES"
    assert result.anomaly_score is None and result.classification is AnomalyClass.UNDETERMINED


def test_low_quality_abstains(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[20,21,22],DataQuality.PROVISIONAL).id,base.id)
    assert result.state is AnalysisState.ABSTAINED and result.abstention_reason=="QUALIDADE INADEQUADA"


def test_explainability_and_contributing_factors(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[20,21,22]).id,base.id)
    factor=result.factors[0]
    assert factor.variable_id=="temp" and factor.contribution>0
    assert "Média observada" in factor.explanation and "Não estabelece causa-raiz" in result.explanation


def test_traceability(setup):
    store,_,_,base,engine=setup;current=session(store,[20,21,22]);result=engine.analyze(current.id,base.id)
    assert result.session_id==current.id and result.baseline_id==base.id
    assert len(result.evidence_ids)==3


def test_algorithm_versioning_and_comparison(setup):
    store,baselines,repo,base,_=setup;current=session(store,[20,21,22])
    AnomalyEngine(store,baselines,repo,AlgorithmVersion(version="1.0")).analyze(current.id,base.id)
    AnomalyEngine(store,baselines,repo,AlgorithmVersion(version="1.1",anomaly_threshold=4)).analyze(current.id,base.id)
    comparison=repo.compare_versions(current.id)
    assert [item["version"] for item in comparison]==["1.0","1.1"]


def test_audit(setup):
    store,_,repo,base,engine=setup;result=engine.analyze(session(store,[20,21,22]).id,base.id)
    assert repo.audit(result.id)[0]["action"]=="ANÁLISE REGISTRADA"


def test_preserves_original_evidence(setup):
    store,_,_,base,engine=setup;current=session(store,[20,21,22]);before=hashlib.sha256(store.path.read_bytes()).hexdigest();engine.analyze(current.id,base.id)
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before


def test_no_automatic_causality_or_confirmation(setup):
    store,_,_,base,engine=setup;result=engine.analyze(session(store,[20,21,22]).id,base.id)
    assert result.causality=="NÃO ESTABELECIDA" and result.root_cause=="NÃO DETERMINADA" and result.confirmed_diagnosis=="NÃO DETERMINADO"


def test_requires_validated_baseline(setup):
    store,baselines,repo,_,_=setup;service=BaselineService(store,baselines);candidate=service.create_candidate("ipro","M2",OperationalContext.NORMAL,[session(store,[1,2,3]).id])
    with pytest.raises(ValueError,match="VALIDADO"):
        AnomalyEngine(store,baselines,repo).analyze(session(store,[10,11,12]).id,candidate.id)


def test_behavior_grouping_and_recurring_pattern(setup):
    store,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10.1,10,9.9]);c=session(store,[30,30,30])
    clusters=engine.cluster_sessions([a.id,b.id,c.id],["temp"])
    assert len(clusters)==2 and any(cluster.recurring and len(cluster.session_ids)==2 for cluster in clusters)
    assert all("NÃO É DIAGNÓSTICO" in cluster.interpretation for cluster in clusters)


def test_model_history_persists(setup):
    store,_,repo,base,engine=setup;engine.analyze(session(store,[20,21,22]).id,base.id)
    assert len(repo.list())==1
