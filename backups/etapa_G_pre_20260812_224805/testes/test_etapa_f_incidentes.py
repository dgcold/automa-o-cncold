import hashlib

import pytest

from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore, TimelineKind, TimelineRecord
from ipro_bench.incident_analysis import IncidentAnalyzer, WindowPreset

BASE=1_900_000_000_000_000_000


def add(store,sid,kind,seconds,name="",variable=None,value=None,quality="VÁLIDA",message=""):
    ns=BASE+int(seconds*1e9)
    return store.append(sid,TimelineRecord(kind,f"2030-03-17T00:{int(seconds)//60:02d}:{int(seconds)%60:02d}+00:00",ns,variable,name,value,quality=quality,message=message,evidence={"source":"offline"}))


def incident(store, *, alarm_name="BAIXA_PRESSAO", recovery=True, comm_loss=False, concurrent=False):
    recorder=BlackBoxRecorder(store);session=recorder.start("ipro","Falha offline")
    add(store,session.id,TimelineKind.SAMPLE,0,"Sucção","pressao_succao",5)
    deviation=add(store,session.id,TimelineKind.DEVIATION,100,"Queda","pressao_succao",3,message="Desvio explícito")
    if comm_loss:add(store,session.id,TimelineKind.COMMUNICATION_LOSS,110,"Driver",message="Perda")
    alarm=add(store,session.id,TimelineKind.ALARM,120,alarm_name,alarm_name,True,message="Alarme")
    if concurrent:add(store,session.id,TimelineKind.STATE_CHANGE,120.5,"Compressor","compressor",False)
    add(store,session.id,TimelineKind.STATE_CHANGE,130,"Compressor","compressor",True,message="Retorno")
    if recovery:add(store,session.id,TimelineKind.RECOVERY,150,"Recuperação",message="Normalizou")
    add(store,session.id,TimelineKind.SAMPLE,160,"Sucção","pressao_succao",5)
    recorder.stop();return session,alarm,deviation


@pytest.fixture
def setup(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3");return store,IncidentAnalyzer(store)


def test_first_deviation_before_alarm(setup):
    store,analyzer=setup;session,alarm,deviation=incident(store)
    result=analyzer.investigate(session.id,alarm)
    assert result.first_deviation["id"]==deviation
    assert result.event["id"]==alarm
    assert result.causality=="NÃO ESTABELECIDA" and result.diagnosis=="NÃO DETERMINADO"


@pytest.mark.parametrize("preset,seconds",[(WindowPreset.SECONDS_30,30),(WindowPreset.MINUTE_1,60),(WindowPreset.MINUTES_5,300),(WindowPreset.MINUTES_15,900)])
def test_pre_post_windows(setup,preset,seconds):
    store,analyzer=setup;session,alarm,_=incident(store)
    result=analyzer.investigate(session.id,alarm,preset)
    assert result.window.start_ns==BASE+(120-seconds)*1_000_000_000
    assert result.window.end_ns==BASE+(120+seconds)*1_000_000_000


def test_full_session_window(setup):
    store,analyzer=setup;session,alarm,_=incident(store)
    result=analyzer.investigate(session.id,alarm,WindowPreset.FULL_SESSION)
    assert result.window.before and result.window.after


def test_recovery_return_and_duration(setup):
    store,analyzer=setup;session,alarm,_=incident(store)
    result=analyzer.investigate(session.id,alarm)
    assert result.first_return["timestamp_ns"]==BASE+130_000_000_000
    assert result.recovery["timestamp_ns"]==BASE+150_000_000_000
    assert result.duration_seconds==30


def test_simultaneous_events(setup):
    store,analyzer=setup;session,alarm,_=incident(store,concurrent=True)
    result=analyzer.investigate(session.id,alarm)
    assert any(row["variable_id"]=="compressor" for row in result.concurrent_events)


def test_insufficient_data_quality(setup):
    store,analyzer=setup;recorder=BlackBoxRecorder(store);session=recorder.start("ipro","Sem dados")
    alarm=add(store,session.id,TimelineKind.ALARM,10,"ALARME","alarm",True);recorder.stop()
    result=analyzer.investigate(session.id,alarm)
    assert result.quality_score==0 and result.first_deviation is None


def test_communication_loss_and_restore(setup):
    store,analyzer=setup;session,alarm,_=incident(store,comm_loss=True)
    result=analyzer.investigate(session.id,alarm)
    assert any(row["kind"]=="PERDA DE COMUNICAÇÃO" for row in result.communication_events)


def test_compare_similar_events_across_sessions(setup):
    store,analyzer=setup;a,alarm_a,_=incident(store);b,alarm_b,_=incident(store)
    comparison=analyzer.compare_events([(a.id,alarm_a),(b.id,alarm_b)])
    assert comparison.occurrences==2 and comparison.event_key=="ALARME::BAIXA_PRESSAO"
    assert comparison.common_preceding_variables==("pressao_succao",)
    assert "NÃO É CAUSALIDADE" in comparison.conclusion


def test_rejects_different_event_types(setup):
    store,analyzer=setup;a,alarm_a,_=incident(store,alarm_name="A");b,alarm_b,_=incident(store,alarm_name="B")
    with pytest.raises(ValueError,match="não são semelhantes"):
        analyzer.compare_events([(a.id,alarm_a),(b.id,alarm_b)])


def test_intermittent_failure_across_sessions(setup):
    store,analyzer=setup;a,_,_=incident(store);b,_,_=incident(store)
    failures=analyzer.intermittent_failures([a.id,b.id])
    assert len(failures)==1 and failures[0].occurrences==2 and failures[0].session_count==2
    assert failures[0].cause=="NÃO DETERMINADA"


def test_single_occurrence_is_not_intermittent(setup):
    store,analyzer=setup;a,_,_=incident(store)
    assert analyzer.intermittent_failures([a.id])==[]


def test_blackbox_and_evidence_are_preserved(setup):
    store,analyzer=setup;session,alarm,_=incident(store)
    before=hashlib.sha256(store.path.read_bytes()).hexdigest();result=analyzer.investigate(session.id,alarm);after=hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert before==after and alarm in result.evidence_ids


def test_no_automatic_hypothesis_or_diagnosis(setup):
    store,analyzer=setup;session,alarm,_=incident(store)
    result=analyzer.investigate(session.id,alarm)
    assert result.hypotheses==("NÃO CONFIRMADAS",)
    assert result.diagnosis=="NÃO DETERMINADO"
