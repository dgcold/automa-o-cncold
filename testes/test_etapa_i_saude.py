import hashlib

import pytest

from ipro_bench.anomaly_analysis import AnomalyEngine, AnomalyRepository
from ipro_bench.baseline import BaselineRepository, BaselineService, BaselineStatus, OperationalContext
from ipro_bench.core import DataQuality
from ipro_bench.defrost_analysis import DefrostCycleAnalyzer
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore, TimelineKind, TimelineRecord
from ipro_bench.operational_health import HealthClassification, HealthDimension, HealthRepository, OperationalHealthEngine, PeriodKind
from ipro_bench.telemetry import TelemetrySample


def session(store,values,variable="temp_camara",quality=DataQuality.VALID,alarm=False):
    recorder=BlackBoxRecorder(store);item=recorder.start("ipro","offline")
    for index,value in enumerate(values):recorder.ingest([TelemetrySample(variable,variable,"PROCESSO","°C",value,quality,"OFFLINE",True,f"2033-01-01T00:00:0{index}+00:00")])
    if alarm:recorder.alarm("alarm",True,"alarme")
    recorder.stop();return item


@pytest.fixture
def setup(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3");bases=BaselineRepository(tmp_path/"base.sqlite3");anomalies=AnomalyRepository(tmp_path/"ai.sqlite3");health=HealthRepository(tmp_path/"health.sqlite3")
    service=BaselineService(store,bases);ref=session(store,[9,10,11,10]);base=service.create_candidate("ipro","M1",OperationalContext.NORMAL,[ref.id]);bases.transition(base.id,BaselineStatus.VALIDATED,"eng")
    engine=OperationalHealthEngine(store,anomalies,DefrostCycleAnalyzer(store,bases),health)
    return store,bases,anomalies,health,base,engine


def test_trend_and_period(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10,10,10],alarm=True)
    report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    alarm=next(t for t in report.trends if t.name=="ALARMES")
    assert alarm.direction=="AUMENTANDO" and report.period_start<=report.period_end


def test_custom_period_requires_bounds(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10])
    with pytest.raises(ValueError,match="início e fim"):engine.analyze("M1","ipro",[a.id],PeriodKind.CUSTOM)


def test_recurrence_normal_signature(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10.1,10,9.9])
    change=engine.compare_signatures(engine.signature(b.id),engine.signature(a.id))
    assert change.classification=="ASSINATURA RECORRENTE"


def test_changed_signature(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[30,30,30])
    change=engine.compare_signatures(engine.signature(b.id),engine.signature(a.id))
    assert change.classification=="ASSINATURA ALTERADA" and change.changed_features
    assert "NÃO É FALHA CONFIRMADA" in change.conclusion


def test_degradation_indicated_from_persistent_anomalies(setup):
    store,bases,anomalies,_,base,engine=setup;sessions=[session(store,[10,10,10]),session(store,[15,16,17]),session(store,[25,26,27])]
    ai=AnomalyEngine(store,bases,anomalies)
    for item in sessions:ai.analyze(item.id,base.id)
    report=engine.analyze("M1","ipro",[s.id for s in sessions],PeriodKind.SESSION)
    general=next(i for i in report.indicators if i.dimension is HealthDimension.GENERAL)
    assert any(t.name=="ANOMALIAS" and t.direction=="AUMENTANDO" for t in report.trends)
    assert general.classification in (HealthClassification.DEGRADATION_INDICATED,HealthClassification.ATTENTION,HealthClassification.BEHAVIOR_CHANGE)
    assert general.probability=="NÃO É PROBABILIDADE DE FALHA"


def test_insufficient_sessions(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);report=engine.analyze("M1","ipro",[a.id],PeriodKind.SESSION)
    general=next(i for i in report.indicators if i.dimension is HealthDimension.GENERAL)
    assert general.classification is HealthClassification.INSUFFICIENT and general.score is None


def test_bad_quality(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10],quality=DataQuality.PROVISIONAL);b=session(store,[10,10,10],quality=DataQuality.PROVISIONAL)
    report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION);data=next(i for i in report.indicators if i.dimension is HealthDimension.DATA)
    assert data.score==0 and data.classification is HealthClassification.DEGRADATION_INDICATED


def test_electrical_health_without_data(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10,10,10]);report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    electrical=next(i for i in report.indicators if i.dimension is HealthDimension.ELECTRICAL)
    assert electrical.classification is HealthClassification.NOT_CONNECTED and electrical.score is None


def test_compressor_health_without_data(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10,10,10]);report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    compressor=next(i for i in report.indicators if i.dimension is HealthDimension.COMPRESSOR)
    assert compressor.classification is HealthClassification.NOT_CONNECTED


def test_preserves_evidence(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10,10,10]);before=hashlib.sha256(store.path.read_bytes()).hexdigest();engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before


def test_explainability_and_evidence_links(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10],alarm=True);b=session(store,[10,10,10]);report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    control=next(i for i in report.indicators if i.dimension is HealthDimension.CONTROL)
    assert control.reasons and control.evidence_ids and "não estima falha" in control.explanation


def test_no_automatic_diagnosis(setup):
    store,_,_,_,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[30,30,30]);report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    assert report.diagnosis=="NÃO DETERMINADO" and report.failure_probability=="NÃO CALCULADA"


def test_health_history_and_audit(setup):
    store,_,_,repo,_,engine=setup;a=session(store,[10,10,10]);b=session(store,[10,10,10]);report=engine.analyze("M1","ipro",[a.id,b.id],PeriodKind.SESSION)
    assert repo.list()[0]["id"]==report.id and repo.audit(report.id)[0]["action"]=="RELATÓRIO GERADO"


def test_electrical_signature_ready_when_normalized_data_exists(setup):
    store,_,_,_,_,engine=setup;a=session(store,[1,2,3],variable="current_total");signature=engine.signature(a.id)
    assert "current_total" in signature.variables
