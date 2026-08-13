import hashlib

import pytest

from ipro_bench.baseline import BaselineRepository, BaselineService, BaselineStatus, OperationalContext
from ipro_bench.core import DataQuality
from ipro_bench.defrost_analysis import CycleStatus, DefrostCycleAnalyzer, EvidenceLevel
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore, TimelineKind, TimelineRecord
from ipro_bench.telemetry import TelemetrySample


BASE = 1_800_000_000_000_000_000


def record(store, session_id, kind, offset, name="", variable=None, value=None, quality="", evidence=None):
    ns = BASE + int(offset * 1e9)
    store.append(session_id, TimelineRecord(kind, f"2027-01-15T00:00:{int(offset):02d}+00:00", ns, variable, name, value, quality=quality, evidence=evidence or {}))


def complete_cycle(store, temperatures=(0, 5, 10, 3), *, complete=True, quality="VÁLIDA", deviation=False):
    recorder = BlackBoxRecorder(store)
    session = recorder.start("ipro", "Degelo offline")
    record(store, session.id, TimelineKind.SAMPLE, 0, "Temperatura", "temp_degelo", temperatures[0], quality, {"unit":"°C"})
    record(store, session.id, TimelineKind.MARKER, 10, "DEGELO_INICIO")
    record(store, session.id, TimelineKind.SAMPLE, 15, "Temperatura", "temp_degelo", temperatures[1], quality, {"unit":"°C"})
    record(store, session.id, TimelineKind.STATE_CHANGE, 16, "Compressor", "compressor", False, quality)
    record(store, session.id, TimelineKind.SAMPLE, 20, "Temperatura", "temp_degelo", temperatures[2], quality, {"unit":"°C"})
    if deviation:
        record(store,session.id,TimelineKind.DEVIATION,18,"Desvio","temp_degelo",12,"VÁLIDA",{"rule":"manual"})
    if complete:
        record(store, session.id, TimelineKind.MARKER, 30, "DEGELO_FIM")
        record(store, session.id, TimelineKind.MARKER, 35, "GOTEJAMENTO_FIM")
        record(store, session.id, TimelineKind.MARKER, 40, "RETORNO_REFRIGERACAO")
        record(store, session.id, TimelineKind.MARKER, 50, "RECUPERACAO")
    record(store, session.id, TimelineKind.SAMPLE, 55, "Temperatura", "temp_degelo", temperatures[3], quality, {"unit":"°C"})
    recorder.stop()
    return session


@pytest.fixture
def setup(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    return store, DefrostCycleAnalyzer(store)


def test_identifies_cycle_start_end_and_duration(setup):
    store, analyzer = setup
    cycle = analyzer.identify(complete_cycle(store).id)[0]
    assert cycle.status is CycleStatus.COMPLETE
    assert cycle.start_ns == BASE + 10_000_000_000
    assert cycle.end_ns == BASE + 30_000_000_000
    assert cycle.duration_seconds == 20


def test_drip_return_and_recovery(setup):
    store, analyzer = setup
    cycle = analyzer.identify(complete_cycle(store).id)[0]
    assert [phase.phase.value for phase in cycle.phases] == ["DEGELO","GOTEJAMENTO","RETORNO À REFRIGERAÇÃO","RECUPERAÇÃO"]
    assert cycle.recovery_seconds == 20


def test_temperature_before_during_after(setup):
    store, analyzer = setup
    summary = analyzer.identify(complete_cycle(store).id)[0].temperatures[0]
    assert summary.before_average == 0
    assert summary.during_average == 7.5
    assert summary.after_average == 3
    assert (summary.during_minimum, summary.during_maximum) == (5,10)


def test_state_events_are_preserved(setup):
    store, analyzer = setup
    cycle = analyzer.identify(complete_cycle(store).id)[0]
    assert cycle.state_events[0]["variable_id"] == "compressor"


def test_incomplete_cycle_is_explicit(setup):
    store, analyzer = setup
    cycle = analyzer.identify(complete_cycle(store, complete=False).id)[0]
    assert cycle.status is CycleStatus.INCOMPLETE
    assert "DEGELO_FIM" in cycle.missing
    assert cycle.duration_seconds is None


def test_no_start_means_no_invented_cycle(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder = BlackBoxRecorder(store); session=recorder.start("ipro","Sem degelo"); recorder.stop()
    assert DefrostCycleAnalyzer(store).identify(session.id) == []


def test_insufficient_samples_are_explicit(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    recorder=BlackBoxRecorder(store);session=recorder.start("ipro","Vazio")
    for offset,label in ((10,"DEGELO_INICIO"),(20,"DEGELO_FIM"),(25,"GOTEJAMENTO_FIM"),(30,"RETORNO_REFRIGERACAO"),(40,"RECUPERACAO")):
        record(store,session.id,TimelineKind.MARKER,offset,label)
    recorder.stop()
    assert DefrostCycleAnalyzer(store).identify(session.id)[0].status is CycleStatus.INSUFFICIENT


def test_cycle_comparison(setup):
    store, analyzer = setup
    reference=analyzer.identify(complete_cycle(store,(0,5,10,3)).id)[0]
    current=analyzer.identify(complete_cycle(store,(0,8,14,4)).id)[0]
    differences=analyzer.compare(current,reference)
    assert any(item.metric=="temp_degelo MÉDIA DURANTE" and item.difference==3.5 for item in differences)
    assert all(item.level is EvidenceLevel.OBSERVED_DIFFERENCE for item in differences)
    assert all("NÃO É DIAGNÓSTICO" in item.statement for item in differences)


def test_first_deviation_alarm_and_evidence(setup):
    store, analyzer = setup
    session=complete_cycle(store,deviation=True)
    cycle=analyzer.identify(session.id)[0]
    assert cycle.first_deviation["kind"]=="DESVIO"
    assert cycle.first_deviation["id"] in cycle.evidence_ids


def test_quality_score_detects_bad_quality(setup):
    store, analyzer = setup
    cycle=analyzer.identify(complete_cycle(store,quality="PROVISÓRIA").id)[0]
    assert cycle.quality_score==0


def test_evidence_store_is_not_modified_by_analysis(setup):
    store, analyzer = setup
    session=complete_cycle(store)
    before=hashlib.sha256(store.path.read_bytes()).hexdigest()
    analyzer.identify(session.id)
    after=hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert before==after


def test_comparison_against_validated_defrost_baseline(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3")
    repo=BaselineRepository(tmp_path/"baseline.sqlite3")
    service=BaselineService(store,repo)
    reference=complete_cycle(store,(0,5,6,3))
    candidate=service.create_candidate("ipro","M1",OperationalContext.DEFROST,[reference.id])
    repo.transition(candidate.id,BaselineStatus.VALIDATED,"eng")
    analyzer=DefrostCycleAnalyzer(store,repo)
    current=analyzer.identify(complete_cycle(store,(0,20,22,3)).id)[0]
    differences=analyzer.compare_baseline(current,candidate.id)
    assert differences and differences[0].level is EvidenceLevel.STATISTICAL_INDICATION


def test_non_defrost_baseline_is_rejected(tmp_path):
    store=BlackBoxStore(tmp_path/"box.sqlite3");repo=BaselineRepository(tmp_path/"baseline.sqlite3");service=BaselineService(store,repo)
    session=complete_cycle(store);candidate=service.create_candidate("ipro","M1",OperationalContext.NORMAL,[session.id]);repo.transition(candidate.id,BaselineStatus.VALIDATED,"eng")
    cycle=DefrostCycleAnalyzer(store).identify(session.id)[0]
    with pytest.raises(ValueError,match="DEGELO"):
        DefrostCycleAnalyzer(store,repo).compare_baseline(cycle,candidate.id)
