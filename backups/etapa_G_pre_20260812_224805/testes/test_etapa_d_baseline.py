import hashlib

import pytest

from ipro_bench.baseline import BaselineRepository, BaselineService, BaselineStatus, OperationalContext
from ipro_bench.core import DataQuality
from ipro_bench.field_diagnostics import BlackBoxRecorder, BlackBoxStore
from ipro_bench.telemetry import TelemetrySample


def make_session(store, values=(10, 11, 9), *, controller="ipro", alarm=False, loss=False, quality=DataQuality.VALID):
    recorder = BlackBoxRecorder(store)
    session = recorder.start(controller, "Referência")
    for index, value in enumerate(values):
        recorder.ingest([TelemetrySample("temp", "Temperatura", "PROCESSO", "°C", value, quality, "OFFLINE", True, f"2026-01-01T00:00:0{index}+00:00")])
    if alarm: recorder.alarm("alarme", True, "Falha")
    if loss: recorder.communication(False, "offline")
    recorder.stop()
    return session


@pytest.fixture
def services(tmp_path):
    store = BlackBoxStore(tmp_path / "box.sqlite3")
    repo = BaselineRepository(tmp_path / "baseline.sqlite3")
    return store, repo, BaselineService(store, repo)


def test_valid_session(services):
    store, _, service = services
    session = make_session(store)
    assert service.assess_session(session.id).valid


@pytest.mark.parametrize("kwargs,reason", [
    ({"alarm": True}, "ALARMES RELEVANTES"),
    ({"loss": True}, "PERDA DE COMUNICAÇÃO"),
])
def test_invalid_session(services, kwargs, reason):
    store, _, service = services
    assessment = service.assess_session(make_session(store, **kwargs).id)
    assert not assessment.valid and reason in assessment.reasons


def test_insufficient_data_cannot_create_baseline(services):
    store, _, service = services
    session = make_session(store, values=(10,))
    with pytest.raises(ValueError, match="DADOS INSUFICIENTES"):
        service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [session.id])


def test_candidate_creation_has_statistics_and_context(services):
    store, _, service = services
    session = make_session(store)
    baseline = service.create_candidate("ipro", "M1", OperationalContext.STARTUP, [session.id])
    profile = baseline.profiles[0]
    assert baseline.status is BaselineStatus.CANDIDATE
    assert baseline.context is OperationalContext.STARTUP
    assert (profile.average, profile.minimum, profile.maximum) == (10, 9, 11)
    assert profile.dispersion > 0 and profile.normal_low < profile.normal_high


def test_reject_candidate(services):
    store, repo, service = services
    candidate = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    assert repo.transition(candidate.id, BaselineStatus.REJECTED, "engenheiro").status is BaselineStatus.REJECTED


def test_validate_then_activate(services):
    store, repo, service = services
    candidate = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    validated = repo.transition(candidate.id, BaselineStatus.VALIDATED, "engenheiro")
    active = repo.transition(validated.id, BaselineStatus.ACTIVE, "engenheiro")
    assert active.status is BaselineStatus.ACTIVE
    assert repo.active("ipro", "M1", OperationalContext.NORMAL).id == active.id


def test_archive_and_replace_require_explicit_flow(services):
    store, repo, service = services
    first = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    repo.transition(first.id, BaselineStatus.VALIDATED, "eng")
    repo.transition(first.id, BaselineStatus.ACTIVE, "eng")
    second = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    repo.transition(second.id, BaselineStatus.VALIDATED, "eng")
    with pytest.raises(ValueError, match="Arquive"):
        repo.transition(second.id, BaselineStatus.ACTIVE, "eng")
    repo.transition(first.id, BaselineStatus.ARCHIVED, "eng")
    assert repo.transition(second.id, BaselineStatus.ACTIVE, "eng").status is BaselineStatus.ACTIVE


def test_versioning_is_per_machine_controller_and_context(services):
    store, _, service = services
    one = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    two = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    other = service.create_candidate("ipro", "M1", OperationalContext.DEFROST, [make_session(store).id])
    assert (one.version, two.version, other.version) == (1, 2, 1)


def test_comparison_detects_deviation_with_evidence(services):
    store, repo, service = services
    candidate = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    repo.transition(candidate.id, BaselineStatus.VALIDATED, "eng")
    current = make_session(store, values=(20, 21, 22))
    deviations = service.compare(current.id, candidate.id)
    assert len(deviations) == 1
    assert deviations[0].magnitude > 0
    assert deviations[0].classification == "EVIDÊNCIA SUFICIENTE"
    assert len(deviations[0].evidence_ids) == 3
    assert "NÃO É DIAGNÓSTICO" in deviations[0].conclusion


def test_candidate_cannot_be_used_for_comparison(services):
    store, _, service = services
    candidate = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    with pytest.raises(ValueError, match="VALIDADO"):
        service.compare(make_session(store).id, candidate.id)


def test_original_blackbox_is_preserved(services):
    store, _, service = services
    session = make_session(store)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [session.id])
    after = hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert before == after


def test_empty_session_impossible(services):
    _, _, service = services
    with pytest.raises(ValueError, match="nenhuma sessão"):
        service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [])


def test_different_contexts_never_share_active_reference(services):
    store, repo, service = services
    normal = service.create_candidate("ipro", "M1", OperationalContext.NORMAL, [make_session(store).id])
    defrost = service.create_candidate("ipro", "M1", OperationalContext.DEFROST, [make_session(store).id])
    for item in (normal, defrost):
        repo.transition(item.id, BaselineStatus.VALIDATED, "eng")
        repo.transition(item.id, BaselineStatus.ACTIVE, "eng")
    assert repo.active("ipro", "M1", OperationalContext.NORMAL).id != repo.active("ipro", "M1", OperationalContext.DEFROST).id
