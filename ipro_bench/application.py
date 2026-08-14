from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .anomaly_analysis import AnomalyEngine, AnomalyRepository
from .baseline import BaselineRepository, BaselineService
from .communication import Rs485SimulatorService, TcpReadOnlyService
from .defrost_analysis import DefrostCycleAnalyzer
from .drivers import ControllerRegistry, build_default_registry
from .drivers.em210.driver import EM210Driver, build_em210_drivers
from .electrical import ElectricalMeasurementService
from .evidence import EvidenceStore
from .explainable_diagnostics import (
    DiagnosticRepository,
    ExplainableDiagnosticEngine,
    RuleCatalog,
    deterministic_observation_rules,
)
from .field_diagnostics import BlackBoxRecorder, BlackBoxStore
from .history_store import PersistentHistory
from .incident_analysis import IncidentAnalyzer
from .mapping import ModbusMapRepository
from .operational_health import HealthRepository, OperationalHealthEngine
from .reports import ReportExporter
from .scenario_executor import ScenarioExecutor
from .scenarios import ScenarioManager
from .session_export import DiagnosticSessionExporter
from .settings import ApplicationSettings
from .test_manager import TestManager


@dataclass
class ApplicationServices:
    project_root: Path
    settings: ApplicationSettings
    evidence: EvidenceStore
    history: PersistentHistory
    electrical: ElectricalMeasurementService
    scenario_manager: ScenarioManager
    reports: ReportExporter
    blackbox_store: BlackBoxStore
    blackbox: BlackBoxRecorder
    session_exporter: DiagnosticSessionExporter
    baseline_repository: BaselineRepository
    baseline_service: BaselineService
    controllers: ControllerRegistry
    em210_drivers: tuple[EM210Driver, EM210Driver]
    map_repository: ModbusMapRepository
    test_manager: TestManager
    tcp: TcpReadOnlyService
    rs485: Rs485SimulatorService
    defrost_analyzer: DefrostCycleAnalyzer
    incident_analyzer: IncidentAnalyzer
    diagnostic_repository: DiagnosticRepository
    rule_catalog: RuleCatalog
    diagnostic_engine: ExplainableDiagnosticEngine
    anomaly_repository: AnomalyRepository
    anomaly_engine: AnomalyEngine
    health_repository: HealthRepository
    health_engine: OperationalHealthEngine
    scenario_executor: ScenarioExecutor


def build_application_services(project_root: str | Path, rs485_logger=None) -> ApplicationServices:
    root = Path(project_root)
    settings = ApplicationSettings.load(root / "config" / "application.json")
    evidence = EvidenceStore(root / "evidencias")
    history = PersistentHistory(root / "dados" / "historico.sqlite3")
    reports = ReportExporter(root / "relatorios")
    blackbox_store = BlackBoxStore(root / "dados" / "caixa_preta.sqlite3")
    baseline_repository = BaselineRepository(root / "dados" / "baselines.sqlite3")
    baseline_service = BaselineService(blackbox_store, baseline_repository)
    defrost = DefrostCycleAnalyzer(blackbox_store, baseline_repository)
    diagnostic_repository = DiagnosticRepository(root / "dados" / "diagnosticos.sqlite3")
    rule_catalog = RuleCatalog(root / "config" / "diagnostic_rules.json")
    anomaly_repository = AnomalyRepository(root / "dados" / "anomalias.sqlite3")
    anomaly_engine = AnomalyEngine(blackbox_store, baseline_repository, anomaly_repository)
    health_repository = HealthRepository(root / "dados" / "saude.sqlite3")
    blackbox = BlackBoxRecorder(blackbox_store)
    services = ApplicationServices(
        root, settings, evidence, history, ElectricalMeasurementService(history),
        ScenarioManager(evidence), reports, blackbox_store, blackbox,
        DiagnosticSessionExporter(blackbox_store, root / "relatorios" / "sessoes"),
        baseline_repository, baseline_service, build_default_registry(root), build_em210_drivers(root),
        ModbusMapRepository(root / "config" / "modbus_map.json", root / "config" / "map_history"),
        TestManager(evidence),
        TcpReadOnlyService(settings.ipro.host, settings.ipro.port, settings.ipro.timeout_seconds),
        Rs485SimulatorService(logger=rs485_logger), defrost,
        IncidentAnalyzer(blackbox_store, baseline_service), diagnostic_repository, rule_catalog,
        ExplainableDiagnosticEngine(blackbox_store, diagnostic_repository, rule_catalog.load()+deterministic_observation_rules()),
        anomaly_repository, anomaly_engine, health_repository,
        OperationalHealthEngine(blackbox_store, anomaly_repository, defrost, health_repository),
        ScenarioExecutor(history, blackbox, blackbox_store, reports),
    )
    return services
