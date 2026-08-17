from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .application import build_application_services
from .baseline import (
    BaselineStatus,
    OperationalContext,
)
from .communication import TcpReadOnlyService
from .core import BenchState, ConnectionState, OperationMode
from .explainable_diagnostics import (
    ConclusionState,
)
from .field_diagnostics import (
    TimelineAnalyzer,
    TimelineKind,
)
from .incident_analysis import WindowPreset
from .operational_health import PeriodKind
from .scenario_catalog import default_scenarios
from .scenarios import Scenario
from .test_manager import BenchTest, TestResult
from .technician_diagnostics import (
    ConfirmationDecision, TechnicianConfirmationRepository,
    TechnicianDiagnosticEngine, display_value, technician_label,
)
from .analysis_integration import SessionEvidenceInterpreter
from .defrost_investigation import FAMILY_DESCRIPTIONS, investigate_defrost
from .coil_calculator import CoilGeometry, FinnedCoilCalculator
from .refrigeration_analysis import RefrigerationAnalyzer
from .machine_scan import EngineeringPoint, Measurement, STAGE_ORDER
from .ui_components import MultiSeriesChart
from refrigerantes import REFRIGERANTES

STYLE = """
QMainWindow, QWidget { background: #0b1220; color: #dce6f2; font-family: 'Segoe UI'; font-size: 13px; }
#sidebar { background: #101a2b; border-right: 1px solid #26354b; }
#brand { color: #f2f7fc; font-size: 20px; font-weight: 700; }
#subtitle { color: #7f93ab; font-size: 11px; }
QListWidget { background: transparent; border: 0; outline: 0; padding: 8px; }
QListWidget::item { padding: 11px 12px; margin: 2px 0; border-radius: 5px; color: #aebed0; }
QListWidget::item:selected { background: #1a6da8; color: white; }
#header { background: #101a2b; border-bottom: 1px solid #26354b; }
#title { font-size: 22px; font-weight: 650; color: #f5f8fc; }
#modeBanner { padding: 8px 14px; border-radius: 4px; font-weight: 700; }
QFrame[card="true"] { background: #121e30; border: 1px solid #26354b; border-radius: 7px; }
QFrame[card="true"] QLabel { background: transparent; border: 0; }
#cardTitle { color: #8297af; font-size: 11px; font-weight: 650; }
#cardValue { color: #f4f8fc; font-size: 20px; font-weight: 700; }
#muted { color: #8297af; }
QPushButton { background: #1a6da8; border: 0; border-radius: 4px; padding: 8px 14px; color: white; font-weight: 600; }
QPushButton:hover { background: #2382c4; }
QPushButton:disabled { background: #344052; color: #7d8998; }
QComboBox, QLineEdit { background: #0d1726; border: 1px solid #33445b; border-radius: 4px; padding: 7px; }
QTableWidget { background: #101a2b; alternate-background-color: #121f32; border: 1px solid #26354b; gridline-color: #26354b; }
QHeaderView::section { background: #19273a; color: #aebed0; padding: 7px; border: 0; }
"""


class SimulationThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, executor, scenario) -> None:
        super().__init__()
        self.executor, self.scenario = executor, scenario

    def run(self) -> None:
        try:
            self.completed.emit(self.executor.execute(self.scenario, speed=100, step_seconds=5))
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            self.failed.emit(str(error))


class TcpProbeThread(QThread):
    finished_probe = Signal(dict)

    def __init__(self, service: TcpReadOnlyService) -> None:
        super().__init__()
        self.service = service

    def run(self) -> None:
        self.finished_probe.emit(self.service.test_connection())


class StatusCard(QFrame):
    def __init__(self, title: str, value: str, detail: str) -> None:
        super().__init__()
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title.upper(), objectName="cardTitle")
        self.value_label = QLabel(value, objectName="cardValue")
        self.detail_label = QLabel(detail, objectName="muted")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def update_value(self, value: str, detail: str | None = None) -> None:
        self.value_label.setText(value)
        if detail is not None:
            self.detail_label.setText(detail)


class TrendChart(QWidget):
    """Gráfico leve com estado vazio explícito e sem valores fabricados."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.values: list[float] = []
        self.setMinimumHeight(230)

    def set_values(self, values: list[float]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101a2b"))
        painter.setPen(QColor("#8297af"))
        painter.drawText(16, 26, self.title)
        area = self.rect().adjusted(18, 42, -18, -20)
        painter.setPen(QPen(QColor("#26354b"), 1))
        painter.drawRect(area)
        if not self.values:
            painter.setPen(QColor("#dce6f2"))
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "SEM DADOS · NÃO CONECTADO")
            return
        minimum, maximum = min(self.values), max(self.values)
        span = maximum - minimum or 1.0
        points = []
        for index, value in enumerate(self.values):
            x = area.left() + (index * area.width() / max(1, len(self.values) - 1))
            y = area.bottom() - ((value - minimum) * area.height() / span)
            points.append((int(x), int(y)))
        painter.setPen(QPen(QColor("#35a7ff"), 2))
        for start, end in pairwise(points):
            painter.drawLine(start[0], start[1], end[0], end[1])


class MainWindow(QMainWindow):
    NAVIGATION = (
        "Dashboard", "Sensores", "I/O", "Medição Elétrica", "Modbus", "Mapa",
        "Cenários", "Testes", "Caixa-Preta", "Timeline", "Gráficos", "Histórico", "Evidências",
        "Baseline", "Baseline × Sessão", "Análise de Degelo", "Degelo × Referência", "Investigação de Evento", "Diagnóstico", "Análise IA", "Análise Frigorífica", "Serpentina Aletada", "Saúde da Máquina", "Relatórios",
    ) + ("Varredura da Máquina",)

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.state = BenchState()
        self.services = build_application_services(project_root, self._rs485_log)
        for name in (
            "evidence", "history", "electrical", "scenario_manager", "reports",
            "blackbox_store", "blackbox", "session_exporter", "baseline_repository",
            "baseline_service", "defrost_analyzer", "incident_analyzer",
            "diagnostic_repository", "rule_catalog", "diagnostic_engine",
            "anomaly_repository", "anomaly_engine", "health_repository",
            "health_engine", "controllers", "map_repository", "test_manager", "tcp", "rs485",
            "machine_scan_repository", "machine_scan_analyzer",
        ):
            setattr(self, name, getattr(self.services, name))
        self.state.ipro_ip = self.services.settings.ipro.host
        self.state.tcp_port = self.services.settings.ipro.port
        self.state.unit_id = self.services.settings.ipro.unit_id
        self.active_controller = self.controllers.get("ipro")
        self.technician_diagnostic_engine = TechnicianDiagnosticEngine()
        self.technician_confirmations = TechnicianConfirmationRepository(self.services.project_root / "dados" / "confirmacoes_tecnico.sqlite3")
        self.probe_thread: TcpProbeThread | None = None
        self.setWindowTitle(self.services.settings.name)
        self.resize(1420, 860)
        self.setMinimumSize(1120, 700)
        self.setStyleSheet(STYLE)
        self._build()
        self._set_mode(OperationMode.SIMULATOR)

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(230)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.addWidget(QLabel("CNCold", objectName="brand"))
        side_layout.addWidget(QLabel("iPro Professional Bench", objectName="subtitle"))
        side_layout.addSpacing(22)
        self.navigation = QListWidget()
        self.navigation.addItems(self.NAVIGATION)
        self.navigation.currentRowChanged.connect(self._change_page)
        side_layout.addWidget(self.navigation, 1)
        side_layout.addWidget(QLabel(f"v{self.services.settings.version} · FINAL", objectName="subtitle"))
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 14, 24, 14)
        self.page_title = QLabel("Dashboard", objectName="title")
        header_layout.addWidget(self.page_title)
        header_layout.addStretch()
        self.controller_combo = QComboBox()
        for driver in self.controllers.all():
            self.controller_combo.addItem(driver.identity.display_name, driver.identity.id)
        self.controller_combo.currentIndexChanged.connect(self._select_controller)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([OperationMode.SIMULATOR.value, OperationMode.REAL_READ_ONLY.value])
        self.mode_combo.currentTextChanged.connect(lambda text: self._set_mode(OperationMode(text)))
        self.mode_banner = QLabel(objectName="modeBanner")
        header_layout.addWidget(QLabel("CONTROLADOR", objectName="muted"))
        header_layout.addWidget(self.controller_combo)
        header_layout.addWidget(self.mode_combo)
        header_layout.addWidget(self.mode_banner)
        content_layout.addWidget(header)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._dashboard())
        self.pages.addWidget(self._supervision())
        self.pages.addWidget(self._io_page())
        self.pages.addWidget(self._electrical_page())
        self.pages.addWidget(self._modbus_page())
        self.pages.addWidget(self._map_page())
        self.pages.addWidget(self._scenarios_page())
        self.pages.addWidget(self._tests_page())
        self.pages.addWidget(self._blackbox_page())
        self.pages.addWidget(self._timeline_page())
        self.pages.addWidget(self._trends_page())
        self.pages.addWidget(self._history_page())
        self.pages.addWidget(self._evidence_page())
        self.pages.addWidget(self._baseline_page())
        self.pages.addWidget(self._baseline_compare_page())
        self.pages.addWidget(self._defrost_page())
        self.pages.addWidget(self._defrost_compare_page())
        self.pages.addWidget(self._incident_page())
        self.pages.addWidget(self._diagnostics_page())
        self.pages.addWidget(self._ai_page())
        self.pages.addWidget(self._refrigeration_page())
        self.pages.addWidget(self._coil_page())
        self.pages.addWidget(self._health_page())
        self.pages.addWidget(self._reports_page())
        self.pages.addWidget(self._machine_scan_page())
        content_layout.addWidget(self.pages, 1)
        self.status = QLabel("  Sistema pronto · nenhuma conexão aberta · iPro protegido contra escrita")
        self.status.setFixedHeight(28)
        self.status.setStyleSheet("background:#07101c;color:#7f93ab;border-top:1px solid #26354b")
        content_layout.addWidget(self.status)
        outer.addWidget(content, 1)
        self.navigation.setCurrentRow(0)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        return page, layout

    def _machine_scan_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page); page_layout.setContentsMargins(0, 0, 0, 0); page_layout.setSpacing(0)
        self.scan_scroll_area = QScrollArea(); self.scan_scroll_area.setWidgetResizable(True); self.scan_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scan_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scan_scroll_content = QWidget()
        layout = QVBoxLayout(self.scan_scroll_content); layout.setContentsMargins(24, 14, 24, 20); layout.setSpacing(10)
        self.scan_scroll_area.setWidget(self.scan_scroll_content); page_layout.addWidget(self.scan_scroll_area)
        layout.addWidget(QLabel("VARREDURA TÉCNICA DA MÁQUINA", objectName="title"))
        layout.addWidget(QLabel("CÁLCULO DE ENGENHARIA → VALOR MEDIDO → DESVIO → LOCALIZAÇÃO → EVIDÊNCIAS → HIPÓTESES → VERIFICAÇÕES", objectName="muted"))
        form = QFormLayout()
        form.setVerticalSpacing(7)
        self.scan_chamber = QDoubleSpinBox(); self.scan_chamber.setRange(-80, 60); self.scan_chamber.setValue(-18); self.scan_chamber.setSuffix(" °C")
        self.scan_expected_evap = QDoubleSpinBox(); self.scan_expected_evap.setRange(-80, 40); self.scan_expected_evap.setValue(-27); self.scan_expected_evap.setSuffix(" °C")
        self.scan_observed_evap = QDoubleSpinBox(); self.scan_observed_evap.setRange(-80, 40); self.scan_observed_evap.setValue(-33); self.scan_observed_evap.setSuffix(" °C")
        form.addRow("Câmara", self.scan_chamber); form.addRow("Evaporação — CÁLCULO DE ENGENHARIA", self.scan_expected_evap); form.addRow("Evaporação — VALOR MEDIDO", self.scan_observed_evap)
        layout.addLayout(form)
        layout.addWidget(QLabel("MEDIÇÕES DA MÁQUINA", objectName="title"))
        machine_form = QFormLayout()
        machine_form.setVerticalSpacing(7)
        self.scan_refrigerant = QComboBox(); self.scan_refrigerant.addItem("NÃO INFORMADO", None)
        for refrigerant in REFRIGERANTES: self.scan_refrigerant.addItem(refrigerant, refrigerant)
        self.scan_evap_out_pressure = QLineEdit(); self.scan_evap_out_pressure.setPlaceholderText("vazio = não medido")
        self.scan_evap_out_pressure_unit = QComboBox(); self.scan_evap_out_pressure_unit.addItems(("PSIG", "bar(g)", "kPa(g)"))
        evap_pressure_row = QWidget(); evap_pressure_layout = QHBoxLayout(evap_pressure_row); evap_pressure_layout.setContentsMargins(0, 0, 0, 0); evap_pressure_layout.addWidget(self.scan_evap_out_pressure); evap_pressure_layout.addWidget(self.scan_evap_out_pressure_unit)
        self.scan_evap_out_temperature = QLineEdit(); self.scan_evap_out_temperature.setPlaceholderText("vazio = não medido · °C")
        self.scan_comp_in_pressure = QLineEdit(); self.scan_comp_in_pressure.setPlaceholderText("vazio = não medido")
        self.scan_comp_in_pressure_unit = QComboBox(); self.scan_comp_in_pressure_unit.addItems(("PSIG", "bar(g)", "kPa(g)"))
        comp_pressure_row = QWidget(); comp_pressure_layout = QHBoxLayout(comp_pressure_row); comp_pressure_layout.setContentsMargins(0, 0, 0, 0); comp_pressure_layout.addWidget(self.scan_comp_in_pressure); comp_pressure_layout.addWidget(self.scan_comp_in_pressure_unit)
        self.scan_comp_in_temperature = QLineEdit(); self.scan_comp_in_temperature.setPlaceholderText("vazio = não medido · °C")
        machine_form.addRow("Refrigerante", self.scan_refrigerant)
        machine_form.addRow("SAÍDA DO EVAPORADOR — Pressão", evap_pressure_row); machine_form.addRow("SAÍDA DO EVAPORADOR — Temperatura °C", self.scan_evap_out_temperature)
        machine_form.addRow("ENTRADA DO COMPRESSOR — Pressão", comp_pressure_row); machine_form.addRow("ENTRADA DO COMPRESSOR — Temperatura °C", self.scan_comp_in_temperature)
        layout.addLayout(machine_form)
        layout.addWidget(QLabel("LINHA DE LÍQUIDO — CONTINUAÇÃO DA INVESTIGAÇÃO", objectName="cardTitle"))
        liquid_form = QFormLayout()
        liquid_form.setVerticalSpacing(7)
        self.scan_condenser_out_pressure = QLineEdit(); self.scan_condenser_out_pressure.setPlaceholderText("vazio = não medido · PSIG")
        self.scan_condenser_out_temperature = QLineEdit(); self.scan_condenser_out_temperature.setPlaceholderText("vazio = não medido · °C")
        self.scan_valve_in_pressure = QLineEdit(); self.scan_valve_in_pressure.setPlaceholderText("vazio = não medido · PSIG")
        self.scan_valve_in_temperature = QLineEdit(); self.scan_valve_in_temperature.setPlaceholderText("vazio = não medido · °C")
        liquid_form.addRow("Pressão saída condensador — PSIG", self.scan_condenser_out_pressure); liquid_form.addRow("Temperatura saída condensador — °C", self.scan_condenser_out_temperature)
        liquid_form.addRow("Pressão antes da válvula — PSIG", self.scan_valve_in_pressure); liquid_form.addRow("Temperatura antes da válvula — °C", self.scan_valve_in_temperature)
        layout.addLayout(liquid_form)
        self.scan_pressure_notice = QLabel("Pressão será registrada, mas só será convertida em temperatura de saturação com refrigerante, unidade e propriedades termodinâmicas válidas.", objectName="muted"); self.scan_pressure_notice.setWordWrap(True); layout.addWidget(self.scan_pressure_notice)
        actions = QHBoxLayout()
        manual_button = QPushButton("EXECUTAR / ATUALIZAR VARREDURA"); manual_button.clicked.connect(self._run_machine_scan); actions.addWidget(manual_button)
        simulation_button = QPushButton("CARREGAR DADOS SIMULADOS"); simulation_button.clicked.connect(self._load_scan_simulation); actions.addWidget(simulation_button)
        layout.addLayout(actions)
        self.scan_map = QTableWidget(len(STAGE_ORDER), 2); self.scan_map.setHorizontalHeaderLabels(("MAPA DE VARREDURA", "STATUS")); self.scan_map.horizontalHeader().setStretchLastSection(True)
        self.scan_map.setMinimumHeight(310); self.scan_map.setMaximumHeight(310); self.scan_map.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.scan_map.setFocusPolicy(Qt.FocusPolicy.NoFocus); layout.addWidget(self.scan_map)
        self.scan_result = QTextEdit(); self.scan_result.setReadOnly(True); self.scan_result.setMinimumHeight(440); self.scan_result.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.scan_result.setFocusPolicy(Qt.FocusPolicy.NoFocus); layout.addWidget(self.scan_result)
        return page

    @staticmethod
    def _optional_scan_value(field: QLineEdit) -> float | None:
        text = field.text().strip().replace(",", ".")
        return None if not text else float(text)

    def _load_scan_simulation(self) -> None:
        self.scan_chamber.setValue(-18); self.scan_expected_evap.setValue(-27); self.scan_observed_evap.setValue(-33)
        for field in (self.scan_evap_out_pressure, self.scan_evap_out_temperature, self.scan_comp_in_pressure, self.scan_comp_in_temperature, self.scan_condenser_out_pressure, self.scan_condenser_out_temperature, self.scan_valve_in_pressure, self.scan_valve_in_temperature): field.clear()
        self.scan_refrigerant.setCurrentIndex(0)
        self._run_machine_scan()

    def _run_machine_scan(self) -> None:
        chamber = self.scan_chamber.value(); expected = self.scan_expected_evap.value(); observed = self.scan_observed_evap.value()
        point = EngineeringPoint.create("PONTO 01", chamber, {"evaporation_temperature_c": expected})
        measurements = [Measurement("chamber_temperature_c", chamber, "°C"), Measurement("evaporation_temperature_c", observed, "°C")]
        optional = (
            ("evaporator_outlet_pressure", self.scan_evap_out_pressure, self.scan_evap_out_pressure_unit.currentText()),
            ("evaporator_outlet_temperature_c", self.scan_evap_out_temperature, "°C"),
            ("compressor_inlet_pressure", self.scan_comp_in_pressure, self.scan_comp_in_pressure_unit.currentText()),
            ("compressor_inlet_temperature_c", self.scan_comp_in_temperature, "°C"),
            ("condenser_outlet_pressure", self.scan_condenser_out_pressure, "PSIG"),
            ("condenser_outlet_temperature_c", self.scan_condenser_out_temperature, "°C"),
            ("expansion_valve_inlet_pressure", self.scan_valve_in_pressure, "PSIG"),
            ("expansion_valve_inlet_temperature_c", self.scan_valve_in_temperature, "°C"),
        )
        try:
            for name, field, unit in optional:
                value = self._optional_scan_value(field)
                if value is not None: measurements.append(Measurement(name, value, unit, source="MEDIÇÃO INFORMADA PELO USUÁRIO"))
        except ValueError:
            self.scan_result.setText("MEDIÇÃO INVÁLIDA — use somente valores numéricos nos campos de pressão e temperatura."); return
        result = self.machine_scan_analyzer.analyze((point,), tuple(measurements), refrigerant=self.scan_refrigerant.currentData())
        self.machine_scan_repository.save(result)
        for row, stage in enumerate(result.stages):
            self.scan_map.setItem(row, 0, QTableWidgetItem(stage.name)); self.scan_map.setItem(row, 1, QTableWidgetItem(stage.status.value))
        deviations = "\n".join(f"{item.name}: {item.value:+.1f} {item.unit}" for item in result.deviations) or "NÃO DETERMINADO"
        missing = "\n".join(f"{index}. {item.capitalize()}" for index, item in enumerate(result.missing_measurements, 1)) or "Nenhuma medição adicional para as etapas avaliadas"
        confidence = "NÃO DETERMINADA" if result.confidence is None else f"{result.confidence:.0%}"
        purpose = f"\n\nFINALIDADE\n{result.missing_measurements_purpose}" if result.missing_measurements_purpose else ""
        thermo = result.thermodynamic_note or "Nenhuma conversão pressão → temperatura de saturação foi aplicada."
        received = []
        trace = []
        for item in result.thermodynamic_points:
            gauge = "NÃO INFORMADA" if item.pressure_gauge is None else f"{item.pressure_gauge:.3f} {item.pressure_unit}"
            temperature = "NÃO INFORMADA" if item.measured_temperature_c is None else f"{item.measured_temperature_c:.2f} °C"
            received.append(f"{item.name}: pressão {gauge}; temperatura {temperature}")
            absolute = "NÃO DETERMINADA" if item.pressure_absolute_pa is None else f"{item.pressure_absolute_pa:.2f} Pa(abs)"
            saturation = "NÃO DETERMINADA" if item.saturation_temperature_c is None else f"{item.saturation_temperature_c:.2f} °C"
            superheat = "NÃO DETERMINADO" if item.superheat_k is None else f"{item.superheat_k:.2f} K"
            trace.append(f"{item.name}: {item.status}; pressão absoluta {absolute}; saturação {saturation}; superaquecimento {superheat}")
        requirement = result.continuation_requirement or "Nenhum requisito termodinâmico adicional identificado neste estágio."
        self.scan_result.setText(f"CÁLCULO DE ENGENHARIA\nCâmara: {chamber:.1f} °C\nEvaporação esperada: {expected:.1f} °C\nTD esperado: {chamber-expected:.1f} K\n\nMÁQUINA / VALOR MEDIDO\nCâmara: {chamber:.1f} °C\nEvaporação observada: {observed:.1f} °C\nTD observado: {chamber-observed:.1f} K\n\nDESVIO\n{deviations}\n\nETAPA PRELIMINAR / CONDIÇÃO TÉRMICA GERAL\n{result.preliminary_stage.value}\n\nETAPAS AVALIADAS\n{result.evaluated_stage_count}\n\nLOCALIZAÇÃO FÍSICA DO DESVIO\n{result.deviation_location}\n\nMOTIVO\n{result.localization_reason}\n\nMEDIÇÕES RECEBIDAS\n{chr(10).join(received)}\n\nAVALIAÇÃO TERMODINÂMICA DAS PRESSÕES\n{thermo}\n{chr(10).join(trace)}\n\nMEDIÇÕES NECESSÁRIAS PARA CONTINUAR\n{missing}{purpose}\n\nREQUISITO PARA CONTINUAR\n{requirement}\n\nDIAGNÓSTICO\n{result.diagnosis}\n\nHIPÓTESE PRINCIPAL\n{result.primary_hypothesis}\n\nCONFIANÇA\n{confidence} — {result.confidence_reason}")
        self.scan_result.setMinimumHeight(max(440, self.scan_result.document().blockCount() * 21 + 36))
        self.status.setText(f"  VARREDURA · {result.id} · {result.diagnosis}")

    def _dashboard(self) -> QWidget:
        page, layout = self._page()
        intro = QLabel("Visão operacional da bancada")
        intro.setStyleSheet("font-size:16px;font-weight:600")
        layout.addWidget(intro)
        grid = QGridLayout()
        ipro = self.services.settings.ipro
        serial = self.services.settings.rs485
        self.card_ipro = StatusCard("iPro", "OFFLINE", f"{ipro.host} · Unit {ipro.unit_id} · v107 preservada")
        self.card_controller = self.card_ipro
        self.card_tcp = StatusCard("Modbus TCP", "DESCONECTADO", f"Porta {ipro.port} · FC03/FC04 somente leitura")
        self.card_rs485 = StatusCard("RS485", "INATIVO", f"{serial.port} · {serial.baudrate} · {serial.bytesize}{serial.parity}{serial.stopbits} · não aberta")
        self.card_sim = StatusCard("Simulador", "PRONTO", "Slaves 1/2 · inicialização somente manual")
        self.card_tests = StatusCard("Testes", "0 EXECUTADOS", "0 aprovados · 0 reprovados")
        self.card_evidence = StatusCard("Evidências", str(self.evidence.count()), "Registros JSONL append-only")
        for index, card in enumerate((self.card_ipro, self.card_tcp, self.card_rs485, self.card_sim, self.card_tests, self.card_evidence)):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        notice = QFrame()
        notice.setStyleSheet("background:#11283a;border:1px solid #24567a;border-radius:6px")
        notice_layout = QVBoxLayout(notice)
        notice_layout.addWidget(QLabel("BARREIRA DE SEGURANÇA ATIVA", objectName="cardTitle"))
        notice_layout.addWidget(QLabel("A conexão real aceita exclusivamente FC03 e FC04. Não existem comandos FC05, FC06, FC15, FC16, reset, STOP ou alteração de parâmetros nesta aplicação."))
        layout.addWidget(notice)
        layout.addStretch()
        return page

    def _supervision(self) -> QWidget:
        page, layout = self._page()
        self.sensor_context = QLabel("Sensores · iPro AGUARDANDO MAPA OFICIAL", objectName="title")
        layout.addWidget(self.sensor_context)
        variables = self.map_repository.load()["variables"]
        table = QTableWidget(len(variables), 6)
        table.setHorizontalHeaderLabels(("W1 / VARIÁVEL", "VALOR", "UNIDADE", "QUALIDADE", "FONTE", "TIMESTAMP"))
        for row, variable in enumerate(variables):
            values = (f"W1[{variable['w1_index']}] · {variable['name']}", "—", variable["unit"], "NÃO MAPEADA", "AGUARDANDO MAPA", "—")
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        layout.addWidget(table)
        return page

    def _io_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Entradas e saídas", objectName="title"))
        self.io_context = QLabel("Copeland iPro · AGUARDANDO MAPA OFICIAL · somente leitura", objectName="muted")
        layout.addWidget(self.io_context)
        rows = (
            ("Entradas digitais", "SEM DADOS", "NÃO MAPEADA", "AGUARDANDO MAPA OFICIAL"),
            ("Saídas digitais", "SEM DADOS", "NÃO MAPEADA", "AGUARDANDO MAPA OFICIAL"),
            ("Entradas analógicas", "SEM DADOS", "NÃO MAPEADA", "AGUARDANDO MAPA OFICIAL"),
            ("Saídas analógicas", "SEM DADOS", "NÃO MAPEADA", "AGUARDANDO MAPA OFICIAL"),
        )
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(("GRUPO", "ESTADO", "QUALIDADE", "ORIGEM"))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        layout.addWidget(QLabel("Candidatos permanecem separados e não são exibidos como mapa oficial.", objectName="muted"))
        return page

    def _electrical_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Medição Elétrica", objectName="title"))
        snapshot = self.electrical.snapshot()
        self.electrical_status = StatusCard("EM210", "NÃO CONECTADO", "Driver futuro · nenhum hardware aberto")
        layout.addWidget(self.electrical_status)
        self.electrical_table = QTableWidget(len(snapshot.samples), 8)
        self.electrical_table.setHorizontalHeaderLabels(
            ("CANAL", "ATUAL", "MÉDIA", "MÍNIMO", "MÁXIMO", "UNIDADE", "QUALIDADE", "FONTE")
        )
        for row, sample in enumerate(snapshot.samples):
            stats = self.electrical.statistics(sample.channel_id)
            average = "—" if stats["average"] is None else stats["average"]
            minimum = "—" if stats["minimum"] is None else stats["minimum"]
            maximum = "—" if stats["maximum"] is None else stats["maximum"]
            values = (
                sample.name, sample.display_value, average, minimum, maximum,
                sample.unit, sample.quality.value, sample.source,
            )
            for column, value in enumerate(values):
                self.electrical_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.electrical_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.electrical_table)
        layout.addWidget(QLabel("Corrente total, compressor e L1/L2/L3 preparados. Valores só aparecem após leitura real de um driver autorizado.", objectName="muted"))
        return page

    def _modbus_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Comunicação", objectName="title"))
        layout.addWidget(QLabel("As ações abaixo são explícitas. Abrir esta tela não toca na rede nem na COM8.", objectName="muted"))
        ipro = self.services.settings.ipro
        serial = self.services.settings.rs485
        tcp = StatusCard("Modbus TCP / iPro real", "SOMENTE LEITURA", f"{ipro.host}:{ipro.port} · Unit {ipro.unit_id} · whitelist FC03/FC04")
        tcp_layout = tcp.layout()
        self.tcp_button = QPushButton("Testar conexão TCP")
        self.tcp_button.clicked.connect(self._probe_tcp)
        tcp_layout.addWidget(self.tcp_button)
        layout.addWidget(tcp)
        rs = StatusCard("Modbus RTU / simulador", "PARADO", f"{serial.port} · {serial.baudrate} · {serial.bytesize} bits · {serial.parity} · {serial.stopbits} stop bits")
        rs_layout = rs.layout()
        controls = QHBoxLayout()
        self.rs_start = QPushButton("Iniciar simulador RS485")
        self.rs_stop = QPushButton("Parar simulador")
        self.rs_stop.setEnabled(False)
        self.rs_start.clicked.connect(self._start_rs485)
        self.rs_stop.clicked.connect(self._stop_rs485)
        controls.addWidget(self.rs_start)
        controls.addWidget(self.rs_stop)
        controls.addStretch()
        rs_layout.addLayout(controls)
        layout.addWidget(rs)
        layout.addStretch()
        return page

    def _map_page(self) -> QWidget:
        page, layout = self._page()
        payload = self.map_repository.load()
        validation = self.map_repository.validate_payload(payload)
        layout.addWidget(QLabel("Mapa Modbus", objectName="title"))
        self.map_context = QLabel(f"CANDIDATOS iPro SEPARADOS · {payload['metadata']['status']} · {validation.variable_count} variáveis · SHA-256 {validation.sha256[:16]}…", objectName="muted")
        layout.addWidget(self.map_context)
        table = QTableWidget(len(payload["variables"]), 7)
        table.setHorizontalHeaderLabels(("VARIÁVEL", "W1", "UNIT", "FC", "ENDEREÇO", "ESCALA", "STATUS"))
        for row, item in enumerate(payload["variables"]):
            values = (item["name"], item["w1_index"], item["unit_id"] or "—", item["function"] or "—", item["address"] if item["address"] is not None else "—", item["scale"], item["status"])
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        import_button = QPushButton("Validar e preparar importação de mapa…")
        import_button.clicked.connect(self._import_map)
        layout.addWidget(import_button, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _scenarios_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Cenários", objectName="title"))
        layout.addWidget(QLabel("Somente cenários offline nesta etapa; execução física permanece bloqueada.", objectName="muted"))
        row = QHBoxLayout()
        self.scenario_name = QLineEdit()
        self.scenario_name.setPlaceholderText("Nome do cenário offline")
        create = QPushButton("Criar cenário")
        create.clicked.connect(self._create_scenario)
        catalog = QPushButton("Carregar 10 cenários")
        catalog.clicked.connect(self._load_scenario_catalog)
        execute = QPushButton("Executar selecionado")
        execute.clicked.connect(self._execute_scenario)
        row.addWidget(self.scenario_name, 1)
        row.addWidget(create)
        row.addWidget(catalog)
        row.addWidget(execute)
        layout.addLayout(row)
        self.scenarios_table = QTableWidget(0, 4)
        self.scenarios_table.setHorizontalHeaderLabels(("ID", "CENÁRIO", "TIPO", "STATUS"))
        self.scenarios_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.scenarios_table)
        self.simulation_status = QLabel("LABORATÓRIO · PRONTO · ORIGEM: SIMULADOR", objectName="muted")
        layout.addWidget(self.simulation_status)
        return page

    def _tests_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Test Manager", objectName="title"))
        row = QHBoxLayout()
        self.test_name = QLineEdit()
        self.test_name.setPlaceholderText("Nome do teste offline")
        create = QPushButton("Criar teste")
        create.clicked.connect(self._create_test)
        row.addWidget(self.test_name, 1)
        row.addWidget(create)
        layout.addLayout(row)
        actions = QHBoxLayout()
        for label, handler in (
            ("Iniciar", self._start_test), ("Aprovar", self._approve_test),
            ("Reprovar", self._fail_test), ("Cancelar", self._cancel_test),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.test_observed = QTextEdit()
        self.test_observed.setPlaceholderText("Resultado observado / notas do operador")
        self.test_observed.setMaximumHeight(80)
        layout.addWidget(self.test_observed)
        self.tests_table = QTableWidget(0, 6)
        self.tests_table.setHorizontalHeaderLabels(("ID", "TESTE", "CATEGORIA", "STATUS", "RESULTADO", "CRIADO EM"))
        self.tests_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tests_table)
        return page

    def _trends_page(self) -> QWidget:
        page, layout = self._page()
        controls=QHBoxLayout();self.historical_session=QLineEdit();self.historical_session.setPlaceholderText("Sessão histórica DIA-* ou execução EXE-*")
        load=QPushButton("Carregar sessão histórica");load.clicked.connect(self._load_historical_session)
        self.historical_status=QLabel("TEMPO REAL · SEM DADOS · NÃO CONECTADO",objectName="muted")
        controls.addWidget(self.historical_session,1);controls.addWidget(load);controls.addWidget(self.historical_status);layout.addLayout(controls)
        layout.addWidget(QLabel("Curvas históricas por variável", objectName="title"))
        layout.addWidget(QLabel("Selecione uma ou mais variáveis para comparar na mesma referência temporal.", objectName="muted"))
        self.graph_variables = QListWidget()
        self.graph_variables.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.graph_variables.setMaximumHeight(120)
        self.graph_variables.itemSelectionChanged.connect(self._refresh_graph_selection)
        layout.addWidget(self.graph_variables)
        self.process_chart = MultiSeriesChart("Sessão histórica · curvas selecionadas")
        # Compatibility buffers retained for integrations that consume the former aggregates.
        self.sensor_chart = TrendChart("Sensores e processo")
        self.electrical_chart = TrendChart("Medição elétrica")
        layout.addWidget(self.process_chart, 1)
        return page

    def _refrigeration_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Análise Frigorífica", objectName="title"))
        layout.addWidget(QLabel("Apoio técnico: o resultado não confirma carga baixa ou vazamento sem verificação física.", objectName="muted"))
        form = QFormLayout()
        self.refrigerant = QComboBox(); self.refrigerant.addItems(REFRIGERANTES)
        self.suction_pressure = self._numeric_input(0, 1000, 1)
        self.suction_temperature = self._numeric_input(-100, 200, 1)
        self.discharge_pressure = self._numeric_input(0, 1500, 1)
        self.liquid_temperature = self._numeric_input(-100, 200, 1)
        for label, widget in (("Refrigerante", self.refrigerant), ("Pressão de sucção (psig)", self.suction_pressure),
                              ("Temperatura da sucção (°C)", self.suction_temperature),
                              ("Pressão de condensação (psig)", self.discharge_pressure),
                              ("Temperatura da linha de líquido (°C)", self.liquid_temperature)):
            form.addRow(label, widget)
        layout.addLayout(form)
        calculate = QPushButton("Calcular superaquecimento e subresfriamento")
        calculate.clicked.connect(self._calculate_refrigeration); layout.addWidget(calculate)
        self.refrigeration_result = QTextEdit(); self.refrigeration_result.setReadOnly(True)
        layout.addWidget(self.refrigeration_result, 1)
        return page

    def _coil_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Calculadora de Serpentina Aletada", objectName="title"))
        layout.addWidget(QLabel("Dimensões em metros; fórmulas e áreas parciais permanecem visíveis para auditoria.", objectName="muted"))
        form = QFormLayout()
        self.coil_tubes = QSpinBox(); self.coil_tubes.setRange(1, 10000)
        self.coil_fins = QSpinBox(); self.coil_fins.setRange(1, 100000)
        self.coil_diameter = self._numeric_input(0.0001, 10, 4)
        self.coil_length = self._numeric_input(0.0001, 100, 3)
        self.coil_height = self._numeric_input(0.0001, 100, 3)
        self.coil_width = self._numeric_input(0.0001, 100, 3)
        self.coil_thickness = self._numeric_input(0.00001, 1, 5)
        for label, widget in (("Tubos", self.coil_tubes), ("Aletas", self.coil_fins),
                              ("Diâmetro externo do tubo", self.coil_diameter), ("Comprimento do tubo", self.coil_length),
                              ("Altura da aleta", self.coil_height), ("Largura da aleta", self.coil_width),
                              ("Espessura da aleta", self.coil_thickness)):
            form.addRow(label, widget)
        layout.addLayout(form)
        calculate = QPushButton("Calcular área de troca"); calculate.clicked.connect(self._calculate_coil); layout.addWidget(calculate)
        self.coil_result = QTextEdit(); self.coil_result.setReadOnly(True); layout.addWidget(self.coil_result, 1)
        return page

    @staticmethod
    def _numeric_input(low: float, high: float, decimals: int) -> QDoubleSpinBox:
        widget = QDoubleSpinBox(); widget.setRange(low, high); widget.setDecimals(decimals)
        return widget

    def _blackbox_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Diagnóstico de Campo · Caixa-Preta", objectName="title"))
        layout.addWidget(QLabel("OFFLINE · aguarda variáveis normalizadas · não inicia nenhum transporte", objectName="muted"))
        self.blackbox_status = StatusCard("Sessão", "PARADA", "NÃO CONECTADO · SEM DADOS")
        layout.addWidget(self.blackbox_status)
        row = QHBoxLayout()
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Identificação da sessão")
        start = QPushButton("Iniciar sessão offline")
        stop = QPushButton("Finalizar sessão")
        marker = QPushButton("Adicionar marcador")
        export = QPushButton("Exportar sessão")
        report = QPushButton("Relatório da sessão")
        start.clicked.connect(self._start_blackbox)
        stop.clicked.connect(self._stop_blackbox)
        marker.clicked.connect(self._add_marker)
        export.clicked.connect(self._export_session)
        report.clicked.connect(self._report_session)
        row.addWidget(self.session_name, 1)
        row.addWidget(start)
        row.addWidget(stop)
        row.addWidget(marker)
        row.addWidget(export)
        row.addWidget(report)
        layout.addLayout(row)
        self.marker_notes = QLineEdit()
        self.marker_notes.setPlaceholderText("Rótulo/observação do marcador")
        layout.addWidget(self.marker_notes)
        self.sessions_table = QTableWidget(0, 5)
        self.sessions_table.setHorizontalHeaderLabels(("ID", "CONTROLADOR", "NOME", "INÍCIO", "STATUS"))
        self.sessions_table.horizontalHeader().setStretchLastSection(True)
        self.sessions_table.itemSelectionChanged.connect(self._select_historical_session)
        layout.addWidget(self.sessions_table)
        self._refresh_sessions()
        return page

    def _timeline_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("DIAGNÓSTICO DA OCORRÊNCIA", objectName="title"))
        self.technician_diagnostic = QTextEdit(); self.technician_diagnostic.setReadOnly(True); self.technician_diagnostic.setMaximumHeight(250)
        self.technician_diagnostic.setText("STATUS DA MÁQUINA: DADOS INSUFICIENTES\n\nPRIMEIRO DESVIO DETECTADO: NÃO DETERMINADO\n\nAGUARDANDO CONFIRMAÇÃO DO TÉCNICO")
        layout.addWidget(self.technician_diagnostic)
        confirmation=QHBoxLayout(); self.technician_name=QLineEdit(); self.technician_name.setPlaceholderText("Técnico")
        self.technician_note=QLineEdit(); self.technician_note.setPlaceholderText("Observação")
        confirmation.addWidget(self.technician_name); confirmation.addWidget(self.technician_note,1)
        for label,decision in (("Evidência suficiente",ConfirmationDecision.SUFFICIENT),("Descartar hipótese",ConfirmationDecision.REJECTED),("Confirmar manualmente",ConfirmationDecision.CONFIRMED)):
            button=QPushButton(label);button.clicked.connect(lambda checked=False,value=decision:self._confirm_technician_diagnostic(value));confirmation.addWidget(button)
        layout.addLayout(confirmation)
        layout.addWidget(QLabel("EVENTOS RELACIONADOS / REGISTROS BRUTOS", objectName="title"))
        filters = QHBoxLayout()
        self.timeline_variable = QLineEdit()
        self.timeline_variable.setPlaceholderText("Filtrar variável")
        self.timeline_kind = QComboBox()
        self.timeline_kind.addItem("TODOS", None)
        for kind in TimelineKind:
            self.timeline_kind.addItem(kind.value, kind)
        self.timeline_cursor = QLineEdit()
        self.timeline_cursor.setPlaceholderText("Cursor timestamp_ns")
        self.timeline_zoom = QComboBox()
        self.timeline_zoom.addItems(("±5 s", "±30 s", "±5 min", "SESSÃO INTEIRA"))
        refresh = QPushButton("Aplicar filtros")
        refresh.clicked.connect(self._refresh_timeline)
        for widget in (self.timeline_variable, self.timeline_kind, self.timeline_cursor, self.timeline_zoom, refresh):
            filters.addWidget(widget)
        layout.addLayout(filters)
        correlation = QHBoxLayout()
        self.correlation_a = QLineEdit()
        self.correlation_a.setPlaceholderText("Variável A")
        self.correlation_b = QLineEdit()
        self.correlation_b.setPlaceholderText("Variável B")
        calculate = QPushButton("Calcular correlação")
        calculate.clicked.connect(self._calculate_correlation)
        self.correlation_result = QLabel("Correlação: DADOS INSUFICIENTES", objectName="muted")
        correlation.addWidget(self.correlation_a)
        correlation.addWidget(self.correlation_b)
        correlation.addWidget(calculate)
        correlation.addWidget(self.correlation_result, 1)
        layout.addLayout(correlation)
        self.timeline_table = QTableWidget(0, 8)
        self.timeline_table.setHorizontalHeaderLabels(("TEMPO", "EVENTO", "VARIÁVEL", "ANTERIOR", "ATUAL", "QUALIDADE", "SEVERIDADE", "EVIDÊNCIA"))
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.timeline_table)
        return page

    def _history_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Histórico persistente", objectName="title"))
        layout.addWidget(QLabel(f"SQLite append-only · {self.history.count()} amostras", objectName="muted"))
        rows = self.history.query(limit=self.services.settings.analysis.history_page_limit)
        table = QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels(("DATA/HORA", "CANAL", "VALOR", "UNIDADE", "QUALIDADE", "FONTE", "CONEXÃO"))
        for row, item in enumerate(rows):
            values = (item["timestamp"], item["channel_id"], item["value"] if item["value"] is not None else "SEM DADOS", item["unit"], item["quality"], item["source"], "SIM" if item["connected"] else "NÃO")
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        return page

    def _baseline_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Baseline Operacional", objectName="title"))
        layout.addWidget(QLabel("Fluxo obrigatório: SESSÃO → CANDIDATO → VALIDADO → ATIVO", objectName="muted"))
        form = QHBoxLayout()
        self.baseline_machine = QLineEdit()
        self.baseline_machine.setPlaceholderText("Máquina / identificação")
        self.baseline_context = QComboBox()
        self.baseline_context.addItems([context.value for context in OperationalContext])
        self.baseline_sessions = QLineEdit()
        self.baseline_sessions.setPlaceholderText("IDs das sessões, separados por vírgula")
        create = QPushButton("Criar candidato")
        create.clicked.connect(self._create_baseline_candidate)
        for widget in (self.baseline_machine, self.baseline_context, self.baseline_sessions, create):
            form.addWidget(widget)
        layout.addLayout(form)
        actions = QHBoxLayout()
        for label, target in (("Validar", BaselineStatus.VALIDATED), ("Ativar", BaselineStatus.ACTIVE), ("Rejeitar", BaselineStatus.REJECTED), ("Arquivar", BaselineStatus.ARCHIVED)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, status=target: self._baseline_transition(status))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.baseline_status = QLabel("Nenhum baseline selecionado · DADOS INSUFICIENTES", objectName="muted")
        layout.addWidget(self.baseline_status)
        self.baseline_table = QTableWidget(0, 9)
        self.baseline_table.setHorizontalHeaderLabels(("ID", "MÁQUINA/CONTROLADOR", "CONTEXTO", "VERSÃO", "PERÍODO", "SESSÕES", "QUALIDADE", "VARIÁVEIS", "STATUS"))
        self.baseline_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.baseline_table)
        self._refresh_baselines()
        return page

    def _baseline_compare_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Baseline × Sessão Atual", objectName="title"))
        controls = QHBoxLayout()
        self.compare_baseline_id = QLineEdit()
        self.compare_baseline_id.setPlaceholderText("ID baseline validado/ativo")
        self.compare_session_id = QLineEdit()
        self.compare_session_id.setPlaceholderText("ID sessão atual")
        compare = QPushButton("Comparar")
        compare.clicked.connect(self._compare_baseline_session)
        controls.addWidget(self.compare_baseline_id)
        controls.addWidget(self.compare_session_id)
        controls.addWidget(compare)
        layout.addLayout(controls)
        self.baseline_chart = TrendChart("Faixa normal × comportamento atual")
        layout.addWidget(self.baseline_chart)
        self.deviation_table = QTableWidget(0, 8)
        self.deviation_table.setHorizontalHeaderLabels(("VARIÁVEL", "MAGNITUDE", "DURAÇÃO", "PRIMEIRO DESVIO", "CONTEXTO", "QUALIDADE", "CLASSIFICAÇÃO", "EVIDÊNCIAS"))
        self.deviation_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.deviation_table)
        layout.addWidget(QLabel("Desvio estatístico não constitui diagnóstico nem causa-raiz.", objectName="muted"))
        return page

    def _defrost_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Análise de Degelo", objectName="title"))
        controls = QHBoxLayout()
        self.defrost_session = QLineEdit(); self.defrost_session.setPlaceholderText("ID da sessão")
        analyze = QPushButton("Identificar ciclos"); analyze.clicked.connect(self._analyze_defrost)
        controls.addWidget(self.defrost_session, 1); controls.addWidget(analyze)
        layout.addLayout(controls)
        cards = QGridLayout()
        self.defrost_cards = {}
        for index, label in enumerate(("Ciclo selecionado","Baseline de referência","Pré-degelo","Degelo","Gotejamento","Retorno","Recuperação","Qualidade")):
            card = StatusCard(label, "SEM DADOS", "NÃO DETERMINADO")
            self.defrost_cards[label] = card; cards.addWidget(card,index//4,index%4)
        layout.addLayout(cards)
        self.defrost_timeline = TrendChart("Timeline visual do ciclo de degelo")
        layout.addWidget(self.defrost_timeline)
        self.defrost_diagnostic=QTextEdit();self.defrost_diagnostic.setReadOnly(True);self.defrost_diagnostic.setMaximumHeight(150)
        self.defrost_diagnostic.setText("ANÁLISE DO CICLO DE DEGELO\nDADOS INSUFICIENTES")
        layout.addWidget(self.defrost_diagnostic)
        self.defrost_events = QTableWidget(0,6)
        self.defrost_events.setHorizontalHeaderLabels(("FASE/EVENTO","INÍCIO","FIM","DURAÇÃO","QUALIDADE","EVIDÊNCIAS"))
        self.defrost_events.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.defrost_events)
        return page

    def _defrost_compare_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Degelo Atual × Degelo de Referência", objectName="title"))
        row = QHBoxLayout()
        self.defrost_current_session=QLineEdit();self.defrost_current_session.setPlaceholderText("Sessão atual")
        self.defrost_reference_session=QLineEdit();self.defrost_reference_session.setPlaceholderText("Sessão de referência")
        compare=QPushButton("Comparar ciclos");compare.clicked.connect(self._compare_defrost)
        self.defrost_baseline_id=QLineEdit();self.defrost_baseline_id.setPlaceholderText("Baseline DEGELO validado/ativo (opcional)")
        baseline=QPushButton("Comparar baseline");baseline.clicked.connect(self._compare_defrost_baseline)
        for widget in (self.defrost_current_session,self.defrost_reference_session,compare,self.defrost_baseline_id,baseline):row.addWidget(widget)
        layout.addLayout(row)
        self.defrost_compare_chart=TrendChart("Diferenças observadas · não representam causa-raiz")
        layout.addWidget(self.defrost_compare_chart)
        self.defrost_differences=QTableWidget(0,8)
        self.defrost_differences.setHorizontalHeaderLabels(("MÉTRICA","ATUAL","REFERÊNCIA","DIFERENÇA","CATEGORIA","QUALIDADE","EVIDÊNCIAS","CONCLUSÃO"))
        self.defrost_differences.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.defrost_differences)
        return page

    def _incident_page(self) -> QWidget:
        page,layout=self._page()
        layout.addWidget(QLabel("Investigação de Evento",objectName="title"))
        controls=QHBoxLayout()
        self.incident_session=QLineEdit();self.incident_session.setPlaceholderText("ID da sessão")
        self.incident_event=QLineEdit();self.incident_event.setPlaceholderText("ID da evidência/evento")
        self.incident_window=QComboBox();self.incident_window.addItems([item.value for item in WindowPreset])
        investigate=QPushButton("Investigar");investigate.clicked.connect(self._investigate_event)
        for widget in (self.incident_session,self.incident_event,self.incident_window,investigate):controls.addWidget(widget)
        layout.addLayout(controls)
        grid=QGridLayout();self.incident_cards={}
        for index,label in enumerate(("EVENTO","PRIMEIRO DESVIO","ANTES","DURANTE","DEPOIS","RECUPERAÇÃO","EVIDÊNCIAS","QUALIDADE DOS DADOS","HIPÓTESES AINDA NÃO CONFIRMADAS")):
            card=StatusCard(label,"SEM DADOS","NÃO DETERMINADO");self.incident_cards[label]=card;grid.addWidget(card,index//3,index%3)
        layout.addLayout(grid)
        compare=QHBoxLayout()
        self.similar_events=QLineEdit();self.similar_events.setPlaceholderText("Ocorrências sessão:id, sessão:id")
        compare_button=QPushButton("Comparar eventos semelhantes");compare_button.clicked.connect(self._compare_incidents)
        self.intermittent_sessions=QLineEdit();self.intermittent_sessions.setPlaceholderText("Sessões para buscar intermitência")
        intermittent=QPushButton("Buscar falhas intermitentes");intermittent.clicked.connect(self._find_intermittent)
        for widget in (self.similar_events,compare_button,self.intermittent_sessions,intermittent):compare.addWidget(widget)
        layout.addLayout(compare)
        self.incident_timeline=QTableWidget(0,8)
        self.incident_timeline.setHorizontalHeaderLabels(("TEMPO","FASE","TIPO","VARIÁVEL","ANTERIOR","ATUAL","QUALIDADE","EVIDÊNCIA"))
        self.incident_timeline.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.incident_timeline)
        layout.addWidget(QLabel("EVENTO ≠ PRIMEIRO DESVIO ≠ CORRELAÇÃO ≠ EVIDÊNCIA ≠ HIPÓTESE ≠ DIAGNÓSTICO",objectName="muted"))
        return page

    def _ai_page(self) -> QWidget:
        page,layout=self._page();layout.addWidget(QLabel("Análise IA / Anomalias",objectName="title"))
        layout.addWidget(QLabel("Camada estatística adicional · não substitui regras, evidências ou revisão humana",objectName="muted"))
        controls=QHBoxLayout();self.ai_session=QLineEdit();self.ai_session.setPlaceholderText("Sessão")
        self.ai_baseline=QLineEdit();self.ai_baseline.setPlaceholderText("Baseline validado/ativo")
        analyze=QPushButton("Analisar offline");analyze.clicked.connect(self._run_ai_analysis)
        for widget in (self.ai_session,self.ai_baseline,analyze):controls.addWidget(widget)
        layout.addLayout(controls)
        grid=QGridLayout();self.ai_cards={}
        for index,label in enumerate(("Estado da análise","Score de anomalia","Baseline utilizado","Período analisado","Variáveis","Qualidade","Confiança","Abstinência")):
            card=StatusCard(label,"SEM DADOS","NÃO DETERMINADO");self.ai_cards[label]=card;grid.addWidget(card,index//4,index%4)
        layout.addLayout(grid)
        self.ai_explanation=QLabel("DADO REAL ≠ ANÁLISE DETERMINÍSTICA ≠ ANÁLISE IA ≠ HIPÓTESE ≠ DIAGNÓSTICO CONFIRMADO",objectName="muted")
        self.ai_explanation.setWordWrap(True);layout.addWidget(self.ai_explanation)
        self.ai_factors=QTableWidget(0,9)
        self.ai_factors.setHorizontalHeaderLabels(("VARIÁVEL","OBSERVADO","BASELINE","DISTÂNCIA","CONTRIBUIÇÃO","DIREÇÃO","INÍCIO","EVIDÊNCIAS"))
        self.ai_factors.setHorizontalHeaderLabels(("VARIÁVEL/FAMÍLIA","OBSERVADO","REFERÊNCIA","DISTÂNCIA","CONTRIBUIÇÃO","DIREÇÃO","INÍCIO","EVIDÊNCIAS","INTERPRETAÇÃO"))
        self.ai_factors.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.ai_factors)
        layout.addWidget(QLabel("Histórico das análises",objectName="title"))
        self.ai_history=QTableWidget(0,7);self.ai_history.setHorizontalHeaderLabels(("ID","SESSÃO","MODELO","ESTADO","CLASSIFICAÇÃO","SCORE","CONFIANÇA"));self.ai_history.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.ai_history)
        self._refresh_ai_history();return page

    def _health_page(self) -> QWidget:
        page,layout=self._page();layout.addWidget(QLabel("Saúde da Máquina",objectName="title"))
        layout.addWidget(QLabel("Indicadores operacionais explicáveis · não são probabilidade de falha",objectName="muted"))
        controls=QHBoxLayout();self.health_machine=QLineEdit();self.health_machine.setPlaceholderText("Máquina")
        self.health_sessions=QLineEdit();self.health_sessions.setPlaceholderText("Sessões, separadas por vírgula")
        self.health_period=QComboBox();self.health_period.addItems([item.value for item in PeriodKind])
        self.health_start=QLineEdit();self.health_start.setPlaceholderText("Início personalizado ISO")
        self.health_end=QLineEdit();self.health_end.setPlaceholderText("Fim personalizado ISO")
        analyze=QPushButton("Calcular saúde");analyze.clicked.connect(self._run_health_analysis)
        for widget in (self.health_machine,self.health_sessions,self.health_period,self.health_start,self.health_end,analyze):controls.addWidget(widget)
        layout.addLayout(controls)
        grid=QGridLayout();self.health_cards={}
        for index,label in enumerate(("GERAL","CONTROLE","TÉRMICA","DEGELO","COMPRESSOR","ELÉTRICA","COMUNICAÇÃO","SENSORES / DADOS")):
            card=StatusCard(label,"SEM DADOS","NÃO DETERMINADO");self.health_cards[label]=card;grid.addWidget(card,index//4,index%4)
        layout.addLayout(grid)
        charts=QHBoxLayout();self.health_trend_chart=TrendChart("Tendências ao longo das sessões");self.health_signature_chart=TrendChart("Assinaturas operacionais");charts.addWidget(self.health_trend_chart);charts.addWidget(self.health_signature_chart);layout.addLayout(charts)
        self.health_table=QTableWidget(0,7);self.health_table.setHorizontalHeaderLabels(("DIMENSÃO/TENDÊNCIA","INDICADOR","CLASSIFICAÇÃO","QUALIDADE","DIREÇÃO","MOTIVOS","EVIDÊNCIAS"));self.health_table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.health_table)
        self.health_summary=QLabel("SEM DADOS · EM210 TOTAL/COMPRESSOR NÃO CONECTADOS",objectName="muted");layout.addWidget(self.health_summary)
        return page

    def _evidence_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Evidências", objectName="title"))
        layout.addWidget(QLabel(str(self.project_root / "evidencias"), objectName="muted"))
        from .evidence import EVIDENCE_CATEGORIES
        self.evidence_table = QTableWidget(len(EVIDENCE_CATEGORIES), 2)
        self.evidence_table.setHorizontalHeaderLabels(("CATEGORIA", "REGISTROS"))
        for row, name in enumerate(EVIDENCE_CATEGORIES):
            self.evidence_table.setItem(row, 0, QTableWidgetItem(name.upper()))
            self.evidence_table.setItem(row, 1, QTableWidgetItem(str(self.evidence.count(name))))
        layout.addWidget(self.evidence_table)
        return page

    def _reports_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Relatórios", objectName="title"))
        layout.addWidget(QLabel("Exportação local PDF / CSV / JSON · nenhum dado é enviado externamente.", objectName="muted"))
        buttons = QHBoxLayout()
        for format_name in ("PDF", "CSV", "JSON"):
            button = QPushButton(f"Exportar {format_name}")
            button.clicked.connect(lambda checked=False, fmt=format_name: self._export_report(fmt))
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.report_status = QLabel("Nenhum relatório gerado nesta sessão.", objectName="muted")
        layout.addWidget(self.report_status)
        layout.addStretch()
        return page

    def _diagnostics_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Diagnóstico Explicável", objectName="title"))
        layout.addWidget(QLabel("Hipóteses técnicas rastreáveis · nenhuma causa-raiz automática", objectName="muted"))
        security=QGridLayout()
        for index,(title,value) in enumerate((("Proteção contra escrita","ATIVA · FC03/FC04 apenas"),("Transportes","OFFLINE · COM8 fechada"),("Regras técnicas",f"{len(self.diagnostic_engine.rules)} VALIDADAS"),("Mapa","AGUARDANDO MAPA OFICIAL"))):
            security.addWidget(StatusCard(title,value,"Nenhuma ação automática configurada"),0,index)
        layout.addLayout(security)
        inputs=QHBoxLayout()
        self.diagnostic_session=QLineEdit();self.diagnostic_session.setPlaceholderText("Sessão")
        self.diagnostic_event=QLineEdit();self.diagnostic_event.setPlaceholderText("Evento/evidência")
        self.diagnostic_deviation=QLineEdit();self.diagnostic_deviation.setPlaceholderText("Primeiro desvio")
        self.diagnostic_context=QLineEdit();self.diagnostic_context.setPlaceholderText("Contexto")
        evaluate=QPushButton("Avaliar regras");evaluate.clicked.connect(self._evaluate_diagnostics)
        for widget in (self.diagnostic_session,self.diagnostic_event,self.diagnostic_deviation,self.diagnostic_context,evaluate):inputs.addWidget(widget)
        layout.addLayout(inputs)
        self.diagnostic_facts=QTextEdit();self.diagnostic_facts.setMaximumHeight(70);self.diagnostic_facts.setPlaceholderText('Fatos rastreáveis em JSON: {"fato": [id_evidencia]}')
        layout.addWidget(self.diagnostic_facts)
        actions=QHBoxLayout()
        for label,state in (("Evidência suficiente",ConclusionState.SUFFICIENT_EVIDENCE),("Descartar",ConclusionState.DISCARDED),("Confirmar manualmente",ConclusionState.CONFIRMED)):
            button=QPushButton(label);button.clicked.connect(lambda checked=False,target=state:self._diagnostic_transition(target));actions.addWidget(button)
        self.confirmation_evidence=QLineEdit();self.confirmation_evidence.setPlaceholderText("IDs de confirmação, separados por vírgula")
        actions.addWidget(self.confirmation_evidence);actions.addStretch();layout.addLayout(actions)
        self.diagnostic_summary=QLabel("REGRAS TÉCNICAS: AGUARDANDO VALIDAÇÃO · DIAGNÓSTICO NÃO DETERMINADO",objectName="muted")
        layout.addWidget(self.diagnostic_summary)
        self.hypotheses_table=QTableWidget(0,10)
        self.hypotheses_table.setHorizontalHeaderLabels(("ID","HIPÓTESE","CONFIANÇA","A FAVOR","CONTRA","EVIDÊNCIAS","PRIMEIRO DESVIO","CONTEXTO","FALTA CONFIRMAR","ESTADO"))
        self.hypotheses_table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.hypotheses_table)
        self._refresh_hypotheses()
        return page

    def _placeholder(self, title: str, text: str) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel(title, objectName="title"))
        layout.addWidget(QLabel(text, objectName="muted"))
        layout.addStretch()
        return page

    def _change_page(self, index: int) -> None:
        if index >= 0:
            self.pages.setCurrentIndex(index)
            self.page_title.setText(self.NAVIGATION[index])

    def _select_controller(self, index: int) -> None:
        controller_id = self.controller_combo.itemData(index)
        if not controller_id:
            return
        self.active_controller = self.controllers.get(controller_id)
        snapshot = self.active_controller.snapshot()
        identity = snapshot.identity
        self.card_controller.title_label.setText(identity.display_name.upper())
        self.card_controller.update_value(snapshot.state.value, f"{identity.manufacturer} · {identity.model} · {snapshot.map_status.value}")
        self.sensor_context.setText(f"Sensores · {identity.display_name} · {snapshot.map_status.value}")
        self.io_context.setText(f"{identity.display_name} · {snapshot.map_status.value} · somente leitura")
        self.map_context.setText(f"{identity.display_name} · MAPA OFICIAL VAZIO · {snapshot.map_status.value} · candidatos separados")
        is_ipro = controller_id == "ipro"
        self.tcp_button.setEnabled(is_ipro)
        self.tcp_button.setText("Testar conexão TCP" if is_ipro else "Transporte indisponível · aguardando documentação")
        self.status.setText(f"  {identity.display_name} · {snapshot.state.value} · {snapshot.map_status.value}")

    def _set_mode(self, mode: OperationMode) -> None:
        self.state.set_mode(mode)
        self.mode_banner.setText(mode.value)
        if mode is OperationMode.REAL_READ_ONLY:
            self.mode_banner.setStyleSheet("background:#7a3215;color:#fff0df;padding:8px 14px;border-radius:4px;font-weight:700")
            self.rs_start.setEnabled(False)
            self.status.setText("  MODO REAL · SOMENTE LEITURA · apenas FC03/FC04 permitidas")
        else:
            self.mode_banner.setStyleSheet("background:#155f4b;color:#dcfff3;padding:8px 14px;border-radius:4px;font-weight:700")
            self.rs_start.setEnabled(not self.rs485.active)
            self.status.setText("  MODO SIMULADOR · nenhuma conexão aberta automaticamente")

    def _probe_tcp(self) -> None:
        self.state.tcp_state = ConnectionState.CONNECTING
        self.tcp_button.setEnabled(False)
        self.card_tcp.update_value("CONECTANDO…")
        self.probe_thread = TcpProbeThread(self.tcp)
        self.probe_thread.finished_probe.connect(self._probe_finished)
        self.probe_thread.start()

    def _probe_finished(self, result: dict) -> None:
        connected = result.get("status") == "CONECTADO"
        self.state.tcp_state = ConnectionState.CONNECTED if connected else ConnectionState.ERROR
        self.state.latency_ms = result.get("latencia_ms")
        self.card_tcp.update_value(result.get("status", "ERRO"), f"Latência {result.get('latencia_ms', '—')} ms · sem leitura de registro")
        self.card_ipro.update_value("ACESSÍVEL" if connected else "OFFLINE")
        self.tcp_button.setEnabled(True)
        self.evidence.append("tcp", {"event": "CONNECTION_PROBE", "read_only": True, **result})
        self.card_evidence.update_value(str(self.evidence.count()))

    def _start_rs485(self) -> None:
        if self.state.mode is not OperationMode.SIMULATOR:
            QMessageBox.warning(self, "Operação bloqueada", "O simulador RS485 só pode ser iniciado no modo SIMULADOR.")
            return
        serial = self.services.settings.rs485
        answer = QMessageBox.question(self, f"Abrir {serial.port}", f"Iniciar o respondedor RS485 em {serial.port} / {serial.baudrate} / {serial.bytesize}{serial.parity}{serial.stopbits}?\nA porta não é aberta até esta confirmação.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.rs485.start()
        self.state.rs485_state = ConnectionState.CONNECTING
        self.rs_start.setEnabled(False)
        self.rs_stop.setEnabled(True)
        self.card_rs485.update_value("INICIANDO", f"{serial.port} · {serial.baudrate} · {serial.bytesize}{serial.parity}{serial.stopbits}")

    def _stop_rs485(self) -> None:
        self.rs485.stop()
        self.state.rs485_state = ConnectionState.DISCONNECTED
        self.rs_start.setEnabled(self.state.mode is OperationMode.SIMULATOR)
        self.rs_stop.setEnabled(False)
        self.card_rs485.update_value("INATIVO", "COM8 liberada")

    def _rs485_log(self, message: str) -> None:
        self.evidence.append("rs485", {"event": "RTU_LOG", "message": message})

    def _import_map(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Selecionar mapa Modbus", str(self.project_root), "JSON (*.json)")
        if not source:
            return
        try:
            payload, validation = self.map_repository.validate_file(source)
            if not validation.valid:
                raise ValueError("\n".join(validation.errors))
            differences = self.map_repository.differences(payload)
            staged = self.map_repository.stage(source)
            QMessageBox.information(self, "Mapa preparado", f"Mapa válido com {validation.variable_count} variáveis.\n{len(differences)} diferenças.\n\nPreparado, mas NÃO ativado:\n{staged}")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            QMessageBox.critical(self, "Mapa rejeitado", str(error))

    def _create_test(self) -> None:
        name = self.test_name.text().strip()
        if not name:
            return
        test = self.test_manager.create(BenchTest(name=name, objective="Teste preparado offline", category="BANCADA"))
        row = self.tests_table.rowCount()
        self.tests_table.insertRow(row)
        for col, value in enumerate((test.id, test.name, test.category, test.status.value, test.result.value, test.created_at)):
            self.tests_table.setItem(row, col, QTableWidgetItem(value))
        self.test_name.clear()
        summary = self.test_manager.summary()
        self.card_tests.update_value(f"{summary['TOTAL']} EXECUTADOS", f"{summary['APROVADO']} aprovados · {summary['REPROVADO']} reprovados")
        self.card_evidence.update_value(str(self.evidence.count()))

    def _selected_test(self) -> tuple[int, str] | None:
        row = self.tests_table.currentRow()
        if row < 0 or self.tests_table.item(row, 0) is None:
            QMessageBox.information(self, "Test Manager", "Selecione um teste.")
            return None
        return row, self.tests_table.item(row, 0).text()

    def _refresh_test_row(self, row: int, test) -> None:
        self.tests_table.setItem(row, 3, QTableWidgetItem(test.status.value))
        self.tests_table.setItem(row, 4, QTableWidgetItem(test.result.value))
        summary = self.test_manager.summary()
        self.card_tests.update_value(f"{summary['TOTAL']} TESTES", f"{summary['APROVADO']} aprovados · {summary['REPROVADO']} reprovados")
        self.card_evidence.update_value(str(self.evidence.count()))

    def _start_test(self) -> None:
        selected = self._selected_test()
        if selected:
            row, test_id = selected
            self._refresh_test_row(row, self.test_manager.start(test_id))

    def _approve_test(self) -> None:
        self._finish_selected_test(TestResult.APPROVED)

    def _fail_test(self) -> None:
        self._finish_selected_test(TestResult.FAILED)

    def _finish_selected_test(self, result: TestResult) -> None:
        selected = self._selected_test()
        if selected:
            row, test_id = selected
            observed = self.test_observed.toPlainText().strip() or "Sem observação informada"
            self._refresh_test_row(row, self.test_manager.finish(test_id, result, observed))

    def _cancel_test(self) -> None:
        selected = self._selected_test()
        if selected:
            row, test_id = selected
            self._refresh_test_row(row, self.test_manager.cancel(test_id, self.test_observed.toPlainText().strip()))

    def _create_scenario(self) -> None:
        name = self.scenario_name.text().strip()
        if not name:
            return
        scenario = self.scenario_manager.create(Scenario(name, "Cenário seguro preparado offline"))
        row = self.scenarios_table.rowCount()
        self.scenarios_table.insertRow(row)
        for column, value in enumerate((scenario.id, scenario.name, "OFFLINE", scenario.status.value)):
            self.scenarios_table.setItem(row, column, QTableWidgetItem(value))
        self.scenario_name.clear()
        self.card_evidence.update_value(str(self.evidence.count()))

    def _append_scenario_row(self, scenario) -> None:
        row = self.scenarios_table.rowCount()
        self.scenarios_table.insertRow(row)
        for column, value in enumerate((scenario.id, scenario.name, "OFFLINE · SIMULADOR", scenario.status.value)):
            self.scenarios_table.setItem(row, column, QTableWidgetItem(value))

    def _load_scenario_catalog(self) -> None:
        existing = {item.name for item in self.scenario_manager.scenarios}
        for scenario in default_scenarios():
            if scenario.name not in existing:
                self.scenario_manager.create(scenario)
                self._append_scenario_row(scenario)
        self.simulation_status.setText("10 CENÁRIOS DISPONÍVEIS · ORIGEM: SIMULADOR")

    def _execute_scenario(self) -> None:
        row = self.scenarios_table.currentRow()
        if row < 0 or self.scenarios_table.item(row, 0) is None:
            self.simulation_status.setText("Selecione um cenário.")
            return
        scenario = self.scenario_manager.get(self.scenarios_table.item(row, 0).text())
        if scenario.status.value == "RASCUNHO":
            self.scenario_manager.mark_ready(scenario.id)
        self.scenario_manager.start_offline(scenario.id)
        self.simulation_status.setText("EM EXECUÇÃO · 100x · ORIGEM: SIMULADOR")
        self.simulation_thread = SimulationThread(self.services.scenario_executor, scenario)
        self.simulation_thread.completed.connect(lambda result: self._simulation_completed(row, scenario, result))
        self.simulation_thread.failed.connect(lambda message: self.simulation_status.setText(f"ERRO DE EXECUÇÃO · {message}"))
        self.simulation_thread.start()

    def _simulation_completed(self, row, scenario, result) -> None:
        self.scenario_manager.finish(scenario.id)
        self.scenarios_table.setItem(row, 3, QTableWidgetItem(scenario.status.value))
        self.simulation_status.setText(
            f"{result.status.value} · {result.execution_id} · {result.session_id} · "
            f"{result.samples} AMOSTRAS · {result.technical_result.value} · ORIGEM: SIMULADOR")

        self.diagnostic_session.setText(result.session_id)
        self.diagnostic_context.setText("SIMULADOR_ELETRICO")
        self.diagnostic_facts.clear()
        self.ai_session.setText(result.session_id)
        self.ai_baseline.clear()

    def _start_blackbox(self) -> None:
        name = self.session_name.text().strip() or "Diagnóstico offline"
        try:
            session = self.blackbox.start(self.active_controller.identity.id, name)
        except ValueError as error:
            QMessageBox.warning(self, "Caixa-Preta", str(error))
            return
        self.blackbox_status.update_value("GRAVANDO", f"{session.id} · SEM DADOS até receber variáveis normalizadas")
        self._refresh_sessions()

    def _stop_blackbox(self) -> None:
        try:
            session = self.blackbox.stop()
        except RuntimeError as error:
            QMessageBox.information(self, "Caixa-Preta", str(error))
            return
        self.blackbox_status.update_value("FINALIZADA", session.id)
        self._refresh_sessions()
        self._refresh_timeline()

    def _add_marker(self) -> None:
        label = self.marker_notes.text().strip()
        if not label:
            return
        try:
            self.blackbox.marker(label)
        except RuntimeError as error:
            QMessageBox.information(self, "Caixa-Preta", str(error))
            return
        self.marker_notes.clear()
        self._refresh_timeline()

    def _refresh_sessions(self) -> None:
        if not hasattr(self, "sessions_table"):
            return
        sessions = self.blackbox_store.sessions()
        self.sessions_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            for column, value in enumerate((session.id, session.controller_id, session.name, session.started_at, session.status.value)):
                self.sessions_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _export_session(self) -> None:
        session_id = self._timeline_session_id()
        if not session_id:
            QMessageBox.information(self, "Caixa-Preta", "Nenhuma sessão disponível.")
            return
        target = self.session_exporter.export_bundle(session_id)
        self.blackbox_status.update_value("EXPORTADA", str(target))

    def _report_session(self) -> None:
        session_id = self._timeline_session_id()
        if not session_id:
            QMessageBox.information(self, "Caixa-Preta", "Nenhuma sessão disponível.")
            return
        target = self.session_exporter.report(session_id)
        self.blackbox_status.update_value("RELATÓRIO GERADO", str(target))

    def _timeline_session_id(self) -> str | None:
        if getattr(self,"historical_session_id",None):return self.historical_session_id
        if self.blackbox.session:
            return self.blackbox.session.id
        sessions = self.blackbox_store.sessions()
        return sessions[0].id if sessions else None

    def _refresh_timeline(self) -> None:
        if not hasattr(self, "timeline_table"):
            return
        session_id = self._timeline_session_id()
        if not session_id:
            self.timeline_table.setRowCount(0)
            return
        variable = self.timeline_variable.text().strip() or None
        selected_kind = self.timeline_kind.currentData()
        kinds = (selected_kind,) if selected_kind else None
        start_ns = end_ns = None
        cursor_text = self.timeline_cursor.text().strip()
        zoom = self.timeline_zoom.currentText()
        if cursor_text and zoom != "SESSÃO INTEIRA":
            try:
                cursor = int(cursor_text)
                seconds = {"±5 s": 5, "±30 s": 30, "±5 min": 300}[zoom]
                start_ns, end_ns = cursor - seconds * 1_000_000_000, cursor + seconds * 1_000_000_000
            except ValueError:
                QMessageBox.warning(self, "Timeline", "Cursor temporal inválido.")
                return
        rows = self.blackbox_store.query(session_id, variable_id=variable, kinds=kinds, start_ns=start_ns, end_ns=end_ns)
        complete_rows = self.blackbox_store.query(session_id)
        facts=SessionEvidenceInterpreter(self.blackbox_store).extract(session_id)
        diagnostic = self.technician_diagnostic_engine.analyze_families(session_id,complete_rows,facts,equipment=self.active_controller.identity.display_name)
        defrost_cycles = self.defrost_analyzer.identify(session_id)
        defrost_text = ""
        if defrost_cycles:
            investigation = investigate_defrost(defrost_cycles[-1], complete_rows)
            family_text = "\n".join(f"- {family}: {FAMILY_DESCRIPTIONS[family]}" for family in investigation.families)
            confidence = "NÃO DETERMINADA" if investigation.confidence is None else f"{investigation.confidence:.0%}"
            defrost_text = "\n\n".join((f"INVESTIGAÇÃO MULTIVARIÁVEL DO DEGELO\n{investigation.conclusion}",
                f"INÍCIO / FIM / DURAÇÃO\n{investigation.start} · {investigation.end} · {display_value(investigation.duration_seconds,'s')}",
                f"VARIÁVEIS\n{', '.join(technician_label(item) for item in investigation.variables) or 'SEM DADOS'}",
                f"FAMÍLIAS DE EVIDÊNCIA\n{family_text or 'SEM DADOS'}",f"CONFIANÇA\n{confidence} · {investigation.confidence_reason}",
                f"REFERÊNCIA\n{investigation.reference}"))
        first=diagnostic.first_deviation
        first_text="NÃO IDENTIFICADO" if first is None else (f"{first.timestamp} | {first.variable} | anterior {display_value(first.previous_value)} | atual {display_value(first.current_value)} | diferença {display_value(first.difference)} | esperado {first.expected} | observado {first.observed} | severidade {first.severity} | evidências {', '.join(map(str,first.evidence_ids))}")
        latest=self.technician_confirmations.latest(session_id); confirmation_text=latest["decision"]+" por "+latest["technician"] if latest else "PENDENTE"
        sections=[f"STATUS DA MÁQUINA\n{diagnostic.machine_status}",f"PRIMEIRO DESVIO DETECTADO\n{first_text}",f"FALHA / ANOMALIA IDENTIFICADA\n{diagnostic.anomaly}",f"O QUE ACONTECEU\n{diagnostic.what_happened}",f"O QUE FOI OBSERVADO\n"+"\n".join(diagnostic.observations),f"EVIDÊNCIAS\n{', '.join(map(str,diagnostic.evidence_ids)) or 'SEM DADOS'}",f"POSSÍVEIS CAUSAS / HIPÓTESES\n"+"\n".join("- "+x for x in diagnostic.hypotheses),f"IMPACTO\n{diagnostic.impact}",f"O QUE O TÉCNICO DEVE VERIFICAR\n"+"\n".join("- "+x for x in diagnostic.recommended_checks),f"CONFIANÇA\n{'NÃO DETERMINADA' if diagnostic.confidence is None else f'{diagnostic.confidence:.0%}'}"]
        if defrost_text:sections.append(defrost_text)
        sections.append(f"DECISÃO DO TÉCNICO (SEPARADA DA ANÁLISE AUTOMÁTICA)\n{confirmation_text}")
        self.technician_diagnostic.setText("\n\n".join(sections))
        self.timeline_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            item = dict(item)
            item["variable_id"] = technician_label(item.get("variable_id"))
            evidence = f"registro #{item['id']}"
            values = (item["timestamp"], item["kind"], item["variable_id"] or "—", item["previous_value"], item["value"], item["quality"] or "—", item["severity"], evidence)
            for column, value in enumerate(values):
                self.timeline_table.setItem(row, column, QTableWidgetItem("SEM DADOS" if value is None else str(value)))

    def _confirm_technician_diagnostic(self,decision:ConfirmationDecision)->None:
        session_id=self._timeline_session_id()
        if not session_id:return
        diagnostic=self.technician_diagnostic_engine.analyze(session_id,self.blackbox_store.query(session_id))
        try:self.technician_confirmations.record(session_id,self.technician_name.text(),diagnostic.anomaly,decision,self.technician_note.text(),diagnostic.evidence_ids)
        except ValueError as error:QMessageBox.warning(self,"Confirmação do técnico",str(error));return
        self._refresh_timeline()

    def _calculate_correlation(self) -> None:
        session_id = self._timeline_session_id()
        variable_a = self.correlation_a.text().strip()
        variable_b = self.correlation_b.text().strip()
        if not session_id or not variable_a or not variable_b:
            self.correlation_result.setText("Correlação: DADOS INSUFICIENTES")
            return
        result = TimelineAnalyzer(self.blackbox_store).correlation(session_id, variable_a, variable_b)
        coefficient = result["coefficient"]
        value = "—" if coefficient is None else f"{coefficient:.4f}"
        self.correlation_result.setText(f"Correlação: {value} · {result['pairs']} pares · {result['status']}")

    def _refresh_baselines(self) -> None:
        if not hasattr(self, "baseline_table"):
            return
        rows = self.baseline_repository.list()
        self.baseline_table.setRowCount(len(rows))
        for row, baseline in enumerate(rows):
            values = (baseline.id, f"{baseline.machine_id} / {baseline.controller_id}", baseline.context.value,
                f"v{baseline.version}", f"{baseline.period_start} → {baseline.period_end}", len(baseline.session_ids),
                f"{baseline.quality_score:.1%}", len(baseline.profiles), baseline.status.value)
            for column, value in enumerate(values):
                self.baseline_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _create_baseline_candidate(self) -> None:
        machine = self.baseline_machine.text().strip()
        sessions = [item.strip() for item in self.baseline_sessions.text().split(",") if item.strip()]
        if not machine:
            self.baseline_status.setText("Máquina não informada · NÃO DETERMINADO")
            return
        try:
            baseline = self.baseline_service.create_candidate(self.active_controller.identity.id, machine,
                OperationalContext(self.baseline_context.currentText()), sessions)
        except (ValueError, KeyError) as error:
            self.baseline_status.setText(str(error))
            return
        self.baseline_status.setText(f"{baseline.id} · CANDIDATO v{baseline.version} · validação manual obrigatória")
        self._refresh_baselines()

    def _selected_baseline_id(self) -> str | None:
        row = self.baseline_table.currentRow()
        return self.baseline_table.item(row, 0).text() if row >= 0 and self.baseline_table.item(row, 0) else None

    def _baseline_transition(self, target: BaselineStatus) -> None:
        baseline_id = self._selected_baseline_id()
        if not baseline_id:
            self.baseline_status.setText("Selecione um baseline.")
            return
        try:
            baseline = self.baseline_repository.transition(baseline_id, target, "OPERADOR DA BANCADA")
        except ValueError as error:
            self.baseline_status.setText(str(error))
            return
        self.baseline_status.setText(f"{baseline.id} · {baseline.status.value} · v{baseline.version}")
        self._refresh_baselines()

    def _compare_baseline_session(self) -> None:
        try:
            deviations = self.baseline_service.compare(self.compare_session_id.text().strip(), self.compare_baseline_id.text().strip())
        except (ValueError, KeyError) as error:
            self.deviation_table.setRowCount(0)
            self.baseline_chart.set_values([])
            self.status.setText(f"  BASELINE × SESSÃO · {error}")
            return
        self.deviation_table.setRowCount(len(deviations))
        for row, deviation in enumerate(deviations):
            values = (deviation.variable_id, deviation.magnitude, deviation.duration_seconds,
                deviation.first_timestamp, deviation.context.value, deviation.quality,
                deviation.classification, ", ".join(map(str, deviation.evidence_ids)))
            for column, value in enumerate(values):
                self.deviation_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.baseline_chart.set_values([item.magnitude for item in deviations])
        self.status.setText(f"  BASELINE × SESSÃO · {len(deviations)} indicações · NÃO É DIAGNÓSTICO")

    def _analyze_defrost(self) -> None:
        try:
            cycles=self.defrost_analyzer.identify(self.defrost_session.text().strip())
        except KeyError as error:
            self.status.setText(f"  DEGELO · sessão inexistente: {error}"); return
        if not cycles:
            self.status.setText("  DEGELO · NENHUM CICLO IDENTIFICADO · SEM DADOS")
            self.defrost_timeline.set_values([]); return
        cycle=cycles[0]
        self.defrost_cards["Ciclo selecionado"].update_value(cycle.id,cycle.status.value)
        self.defrost_cards["Baseline de referência"].update_value("NÃO SELECIONADO","NÃO DETERMINADO")
        phase_map={phase.phase.value:phase for phase in cycle.phases}
        for label,key in (("Degelo","DEGELO"),("Gotejamento","GOTEJAMENTO"),("Retorno","RETORNO À REFRIGERAÇÃO"),("Recuperação","RECUPERAÇÃO")):
            phase=phase_map.get(key);self.defrost_cards[label].update_value(f"{phase.duration_seconds:.1f} s" if phase else "SEM DADOS",phase.phase.value if phase else "NÃO DETERMINADO")
        self.defrost_cards["Pré-degelo"].update_value("15 min","Janela de análise")
        self.defrost_cards["Qualidade"].update_value(f"{cycle.quality_score:.1%}",cycle.status.value)
        self.defrost_timeline.set_values([phase.duration_seconds for phase in cycle.phases])
        diagnostic=self.technician_diagnostic_engine.analyze_defrost(cycle,equipment=self.active_controller.identity.display_name)
        first="NÃO IDENTIFICADO" if diagnostic.first_deviation is None else f"{diagnostic.first_deviation.timestamp} - {diagnostic.first_deviation.variable}"
        self.defrost_diagnostic.setText("\n".join(("ANÁLISE DO CICLO DE DEGELO",f"RESULTADO: {diagnostic.anomaly}",f"PRIMEIRO DESVIO: {first}",*diagnostic.observations,f"MOTIVO / HIPÓTESE: {diagnostic.hypotheses[0]}","CONFIRMAÇÃO DO TÉCNICO: PENDENTE")))
        rows=list(cycle.phases)+list(cycle.alarms)+list(cycle.state_events)
        self.defrost_events.setRowCount(len(rows))
        for row,item in enumerate(rows):
            if hasattr(item,"phase"):
                values=(item.phase.value,item.start_ns,item.end_ns,item.duration_seconds,f"{cycle.quality_score:.1%}",", ".join(map(str,item.evidence_ids)))
            else:
                values=(item["kind"],item["timestamp_ns"],item["timestamp_ns"],0,item["quality"] or "—",item["id"])
            for col,value in enumerate(values):self.defrost_events.setItem(row,col,QTableWidgetItem(str(value)))
        self.status.setText(f"  DEGELO · {len(cycles)} ciclo(s) · {cycle.status.value}")

    def _cycle_from_session(self, session_id: str):
        cycles=self.defrost_analyzer.identify(session_id.strip())
        if not cycles: raise ValueError("Nenhum ciclo de degelo identificado.")
        return cycles[0]

    def _compare_defrost(self) -> None:
        try:
            differences=self.defrost_analyzer.compare(self._cycle_from_session(self.defrost_current_session.text()),self._cycle_from_session(self.defrost_reference_session.text()))
        except (KeyError,ValueError) as error:
            self.status.setText(f"  DEGELO × REFERÊNCIA · {error}");return
        self._show_defrost_differences(differences)

    def _compare_defrost_baseline(self) -> None:
        try:
            differences=self.defrost_analyzer.compare_baseline(self._cycle_from_session(self.defrost_current_session.text()),self.defrost_baseline_id.text().strip())
        except (KeyError,ValueError) as error:
            self.status.setText(f"  DEGELO × BASELINE · {error}");return
        self._show_defrost_differences(differences)

    def _show_defrost_differences(self,differences) -> None:
        self.defrost_differences.setRowCount(len(differences))
        for row,item in enumerate(differences):
            values=(item.metric,item.current,item.reference,item.difference,item.level.value,item.quality,", ".join(map(str,item.evidence_ids)),item.statement)
            for col,value in enumerate(values):self.defrost_differences.setItem(row,col,QTableWidgetItem("SEM DADOS" if value is None else str(value)))
        self.defrost_compare_chart.set_values([abs(item.difference) for item in differences if item.difference is not None])
        self.status.setText(f"  DEGELO · {len(differences)} diferenças · NÃO É DIAGNÓSTICO")

    def _investigate_event(self) -> None:
        if not self.incident_event.text().strip():
            self.status.setText("  Informe um ID de evidência/evento para investigar um evento específico.")
            return
        try:
            result=self.incident_analyzer.investigate(self.incident_session.text().strip(),int(self.incident_event.text().strip()),WindowPreset(self.incident_window.currentText()))
        except (KeyError,ValueError) as error:
            self.status.setText(f"  INVESTIGAÇÃO · {error}");return
        event=result.event;deviation=result.first_deviation
        self.incident_cards["EVENTO"].update_value(event["kind"],event["message"] or event["name"])
        self.incident_cards["PRIMEIRO DESVIO"].update_value(deviation["kind"] if deviation else "NÃO DETERMINADO",deviation["timestamp"] if deviation else "SEM EVIDÊNCIA EXPLÍCITA")
        self.incident_cards["ANTES"].update_value(str(len(result.window.before)),"registros")
        self.incident_cards["DURANTE"].update_value(str(len(result.window.during)),"eventos simultâneos")
        self.incident_cards["DEPOIS"].update_value(str(len(result.window.after)),"registros")
        self.incident_cards["RECUPERAÇÃO"].update_value(result.recovery["timestamp"] if result.recovery else "NÃO DETERMINADA",f"{result.duration_seconds} s" if result.duration_seconds is not None else "SEM DADOS")
        self.incident_cards["EVIDÊNCIAS"].update_value(str(len(result.evidence_ids)),"IDs preservados")
        self.incident_cards["QUALIDADE DOS DADOS"].update_value(f"{result.quality_score:.1%}","calculada sobre amostras existentes")
        self.incident_cards["HIPÓTESES AINDA NÃO CONFIRMADAS"].update_value("NÃO CONFIRMADAS","DIAGNÓSTICO NÃO DETERMINADO")
        rows=[("ANTES",r) for r in result.window.before]+[("DURANTE",r) for r in result.window.during]+[("DEPOIS",r) for r in result.window.after]
        self.incident_timeline.setRowCount(len(rows))
        for row,(phase,item) in enumerate(rows):
            values=(item["timestamp"],phase,item["kind"],item["variable_id"] or item["name"],item["previous_value"],item["value"],item["quality"] or "—",item["id"])
            for col,value in enumerate(values):self.incident_timeline.setItem(row,col,QTableWidgetItem("SEM DADOS" if value is None else str(value)))
        self.status.setText(f"  INVESTIGAÇÃO · {event['kind']} · CAUSALIDADE {result.causality}")

    def _parse_occurrences(self,text):
        result=[]
        for item in text.split(","):
            if not item.strip():continue
            session,event=item.strip().rsplit(":",1);result.append((session,int(event)))
        return result

    def _select_historical_session(self)->None:
        row=self.sessions_table.currentRow()
        if row<0 or not self.sessions_table.item(row,0):return
        identifier=self.sessions_table.item(row,0).text()
        self.historical_session.setText(identifier)
        self._load_historical_session()

    def _prepare_session_views(self, session_id: str, rows: list[dict]) -> None:
        """Propagate one historical session and remove derived data from the previous one."""
        self.historical_session_id=session_id
        for name in ("diagnostic_session","ai_session","incident_session","defrost_session"):
            widget=getattr(self,name,None)
            if widget:widget.setText(session_id)
        events=[row for row in rows if row.get("kind") != TimelineKind.SAMPLE.value]
        self.incident_event.setText(str(events[0]["id"]) if events else "")
        self.incident_timeline.setRowCount(0)
        self.ai_factors.setRowCount(0)
        self.ai_explanation.setText("Sessão alterada. Execute a análise offline para calcular resultados desta sessão.")
        self.diagnostic_summary.setText("Sessão alterada. Avalie as regras desta sessão; nenhum resultado anterior foi reutilizado.")

    def _load_historical_session(self)->None:
        try:session_id=self.blackbox_store.resolve_session_id(self.historical_session.text().strip())
        except (KeyError,ValueError) as error:self.historical_status.setText(f"SESSÃO NÃO ENCONTRADA · {error}");return
        all_rows=self.blackbox_store.query(session_id,limit=self.services.settings.analysis.export_limit)
        rows=[row for row in all_rows if row.get("kind") == TimelineKind.SAMPLE.value]
        sensor_ids={"temperature_chamber","temperature_evaporator","pressure_suction","pressure_discharge"}
        electrical_ids={"current_total","current_compressor","current_l1","current_l2","current_l3"}
        self.sensor_chart.set_values([float(row["value"]) for row in rows if row.get("variable_id") in sensor_ids and isinstance(row.get("value"),(int,float))])
        self.electrical_chart.set_values([float(row["value"]) for row in rows if row.get("variable_id") in electrical_ids and isinstance(row.get("value"),(int,float))])
        self.historical_graph_rows = rows
        self.graph_variables.blockSignals(True); self.graph_variables.clear(); self.process_chart.clear()
        variables=sorted({row.get("variable_id") for row in rows if row.get("variable_id") and isinstance(row.get("value"),(int,float))})
        self.graph_variables.addItems(variables)
        for index in range(min(4, len(variables))): self.graph_variables.item(index).setSelected(True)
        self.graph_variables.blockSignals(False); self._refresh_graph_selection()
        self._prepare_session_views(session_id,all_rows)
        self._refresh_timeline()
        self.historical_status.setText(f"MODO HISTÓRICO · {session_id} · {len(rows)} AMOSTRAS · {len(all_rows)-len(rows)} EVENTOS")

    def _refresh_graph_selection(self) -> None:
        rows = getattr(self, "historical_graph_rows", [])
        selected = {item.text() for item in self.graph_variables.selectedItems()}
        series = {name: [] for name in selected}
        for row in rows:
            name, value, timestamp = row.get("variable_id"), row.get("value"), row.get("timestamp_ns")
            if name in selected and isinstance(value, (int, float)) and isinstance(timestamp, int):
                series[name].append((timestamp, float(value)))
        self.process_chart.set_series(series)

    def _calculate_refrigeration(self) -> None:
        analyzer = RefrigerationAnalyzer()
        refrigerant = self.refrigerant.currentText()
        superheat = analyzer.superheat(self.suction_pressure.value(), self.suction_temperature.value(), refrigerant)
        subcooling = analyzer.subcooling(self.discharge_pressure.value(), self.liquid_temperature.value(), refrigerant)
        assessment = analyzer.assess_charge(superheat, subcooling, suction_pressure_psig=self.suction_pressure.value())
        value = lambda reading: "SEM DADOS" if reading.value_c is None else f"{reading.value_c:.2f} °C"
        confidence = "NÃO DETERMINADA" if assessment.confidence is None else f"{assessment.confidence:.0%}"
        self.refrigeration_result.setText("\n\n".join((
            f"SUPERAQUECIMENTO: {value(superheat)} · {superheat.status.value}\nReferência: {superheat.reference}",
            f"SUBRESFRIAMENTO: {value(subcooling)} · {subcooling.status.value}\nReferência: {subcooling.reference}",
            f"HIPÓTESE CAUTELOSA: {assessment.hypothesis}\nConfiança: {confidence}\nJustificativa: {assessment.confidence_reason}",
            "EVIDÊNCIAS\n" + ("\n".join(f"- {item}" for item in assessment.evidence) or "- Nenhuma relação conclusiva"),
            "ALTERNATIVAS\n" + "\n".join(f"- {item}" for item in assessment.alternatives),
            "VERIFICAÇÃO DO TÉCNICO\n" + "\n".join(f"- {item}" for item in assessment.technician_checks),
        )))

    def _calculate_coil(self) -> None:
        data = CoilGeometry(self.coil_tubes.value(), self.coil_diameter.value(), self.coil_length.value(),
                            self.coil_fins.value(), self.coil_height.value(), self.coil_width.value(), self.coil_thickness.value())
        try: result = FinnedCoilCalculator.calculate(data)
        except ValueError as error: self.coil_result.setText(str(error)); return
        self.coil_result.setText("\n".join((
            f"Área externa dos tubos: {result.tube_external_area_m2:.4f} m²",
            f"Área bruta das aletas: {result.gross_fin_area_m2:.4f} m²",
            f"Área ocupada pelos furos: {result.tube_hole_area_m2:.4f} m²",
            f"Área efetiva das aletas: {result.effective_fin_area_m2:.4f} m²",
            f"ÁREA TOTAL DE TROCA: {result.total_exchange_area_m2:.4f} m²",
            f"Densidade: {result.fin_density_per_m:.2f} aletas/m · {result.fpi:.2f} FPI",
            "", "FÓRMULAS", *result.formula,
        )))

    def _compare_incidents(self) -> None:
        try:result=self.incident_analyzer.compare_events(self._parse_occurrences(self.similar_events.text()))
        except (ValueError,KeyError) as error:self.status.setText(f"  COMPARAÇÃO · {error}");return
        self.status.setText(f"  {result.classification} · {result.occurrences} ocorrências · {result.conclusion}")

    def _find_intermittent(self) -> None:
        sessions=[item.strip() for item in self.intermittent_sessions.text().split(",") if item.strip()]
        try:failures=self.incident_analyzer.intermittent_failures(sessions)
        except KeyError as error:self.status.setText(f"  INTERMITÊNCIA · {error}");return
        self.status.setText(f"  INTERMITÊNCIA · {len(failures)} padrão(ões) · CAUSA NÃO DETERMINADA")

    def _refresh_hypotheses(self) -> None:
        if not hasattr(self,"hypotheses_table"):return
        items=self.diagnostic_repository.list();self.hypotheses_table.setRowCount(len(items))
        references={rule.id:f"Critério {rule.id} v{rule.version}: {rule.description} · fonte: {rule.source}" for rule in self.diagnostic_engine.rules}
        for row,item in enumerate(items):
            contrary="; ".join(a.text for a in item.contrary) or references.get(item.rule_id,"Nenhuma evidência contrária registrada; confirmação física permanece necessária.")
            values=(item.id,item.description,f"{item.confidence:.1%}","; ".join(a.text for a in item.favorable),
                contrary,", ".join(map(str,item.evidence_ids)),item.first_deviation_id or "NÃO DETERMINADO",
                item.context,"; ".join(item.missing_confirmation) or "NENHUMA",item.state.value)
            for col,value in enumerate(values):self.hypotheses_table.setItem(row,col,QTableWidgetItem(str(value)))

    def _evaluate_diagnostics(self) -> None:
        try:
            raw_facts=self.diagnostic_facts.toPlainText().strip()
            if raw_facts:
                facts=json.loads(raw_facts)
                conclusions=self.diagnostic_engine.evaluate(self.diagnostic_session.text().strip(),facts,
                    context=self.diagnostic_context.text().strip() or "SIMULADOR_ELETRICO",event_id=int(self.diagnostic_event.text()) if self.diagnostic_event.text().strip() else None,
                    first_deviation_id=int(self.diagnostic_deviation.text()) if self.diagnostic_deviation.text().strip() else None)
            else:
                conclusions=self.diagnostic_engine.evaluate_recorded(self.diagnostic_session.text().strip(),context=self.diagnostic_context.text().strip() or "SIMULADOR_ELETRICO")
        except (ValueError,KeyError,json.JSONDecodeError) as error:
            self.diagnostic_summary.setText(f"AVALIAÇÃO REJEITADA · {error}");return
        self._refresh_hypotheses()
        self.diagnostic_summary.setText(f"{len(conclusions)} HIPÓTESE(S) · CAUSALIDADE NÃO ESTABELECIDA · DIAGNÓSTICO NÃO DETERMINADO")

    def _selected_hypothesis_id(self):
        row=self.hypotheses_table.currentRow();return self.hypotheses_table.item(row,0).text() if row>=0 and self.hypotheses_table.item(row,0) else None

    def _diagnostic_transition(self,target) -> None:
        hypothesis_id=self._selected_hypothesis_id()
        if not hypothesis_id:self.diagnostic_summary.setText("Selecione uma hipótese.");return
        evidence=tuple(int(item.strip()) for item in self.confirmation_evidence.text().split(",") if item.strip())
        try:result=self.diagnostic_repository.transition(hypothesis_id,target,"OPERADOR DA BANCADA",confirmation_evidence=evidence)
        except ValueError as error:self.diagnostic_summary.setText(str(error));return
        self._refresh_hypotheses();self.diagnostic_summary.setText(f"{result.id} · {result.state.value} · {result.causality}")

    def _run_ai_analysis(self) -> None:
        try:
            baseline=self.ai_baseline.text().strip()
            result=self.anomaly_engine.analyze(self.ai_session.text().strip(),baseline) if baseline else self.anomaly_engine.analyze_recorded(self.ai_session.text().strip())
        except (ValueError,KeyError) as error:self.status.setText(f"  ANÁLISE IA · {error}");return
        self.ai_cards["Estado da análise"].update_value(result.state.value,result.classification.value)
        self.ai_cards["Score de anomalia"].update_value("NÃO DETERMINADO" if result.anomaly_score is None else f"{result.anomaly_score:.1f}/100","ANOMALIA NÃO É CAUSA-RAIZ")
        self.ai_cards["Baseline utilizado"].update_value(result.baseline_id,f"Algoritmo {result.algorithm_version}")
        self.ai_cards["Período analisado"].update_value(result.period_start or "SEM DADOS",result.period_end or "NÃO DETERMINADO")
        self.ai_cards["Variáveis"].update_value(str(len(result.variables)),", ".join(result.variables) or "SEM DADOS")
        self.ai_cards["Qualidade"].update_value(f"{result.quality_score:.1%}","dados existentes")
        self.ai_cards["Confiança"].update_value(f"{result.confidence:.1%}","NÃO É CONFIRMAÇÃO")
        self.ai_cards["Abstinência"].update_value(result.abstention_reason or "NÃO",result.state.value)
        self.ai_explanation.setText(result.explanation+" · CAUSALIDADE "+result.causality+" · DIAGNÓSTICO "+result.confirmed_diagnosis)
        self.ai_factors.setRowCount(len(result.factors))
        for row,item in enumerate(result.factors):
            values=(item.variable_id,item.observed_average,item.baseline_average,item.standardized_distance,item.contribution,item.direction,item.first_anomalous_timestamp or "NÃO DETERMINADO",", ".join("E"+str(value) for value in item.evidence_ids),item.explanation)
            for col,value in enumerate(values):self.ai_factors.setItem(row,col,QTableWidgetItem(str(value)))
        self._refresh_ai_history();self.status.setText(f"  ANÁLISE IA · {result.classification.value} · CAUSA NÃO DETERMINADA")

    def _refresh_ai_history(self) -> None:
        if not hasattr(self,"ai_history"):return
        items=self.anomaly_repository.list();self.ai_history.setRowCount(len(items))
        for row,item in enumerate(items):
            values=(item.id,item.session_id,item.algorithm_version,item.state.value,item.classification.value,item.anomaly_score if item.anomaly_score is not None else "NÃO DETERMINADO",f"{item.confidence:.1%}")
            for col,value in enumerate(values):self.ai_history.setItem(row,col,QTableWidgetItem(str(value)))

    def _run_health_analysis(self) -> None:
        sessions=[item.strip() for item in self.health_sessions.text().split(",") if item.strip()]
        try:report=self.health_engine.analyze(self.health_machine.text().strip() or "NÃO IDENTIFICADA",self.active_controller.identity.id,sessions,PeriodKind(self.health_period.currentText()),self.health_start.text().strip() or None,self.health_end.text().strip() or None)
        except (ValueError,KeyError) as error:self.health_summary.setText(str(error));return
        for indicator in report.indicators:
            card=self.health_cards.get(indicator.dimension.value)
            if card:card.update_value("SEM DADOS" if indicator.score is None else f"{indicator.score:.1f}/100",f"{indicator.classification.value} · qualidade {indicator.quality_score:.1%}")
        trend_values=[abs(item.slope) for item in report.trends if item.slope is not None];self.health_trend_chart.set_values(trend_values)
        self.health_signature_chart.set_values([sum(abs(v) for v in signature.features) for signature in report.signatures])
        rows=[("INDICADOR",item) for item in report.indicators]+[("TENDÊNCIA",item) for item in report.trends]
        self.health_table.setRowCount(len(rows))
        for row,(kind,item) in enumerate(rows):
            if kind=="INDICADOR":values=(item.dimension.value,item.score if item.score is not None else "SEM DADOS",item.classification.value,f"{item.quality_score:.1%}","—","; ".join(item.reasons),", ".join(map(str,item.evidence_ids)))
            else:values=(item.name,"—","TENDÊNCIA","—",item.direction,"persistente" if item.persistent else "não persistente",", ".join(map(str,item.evidence_ids)))
            for col,value in enumerate(values):self.health_table.setItem(row,col,QTableWidgetItem(str(value)))
        self.health_summary.setText(f"{report.period_start} → {report.period_end} · {len(report.session_ids)} sessões · DIAGNÓSTICO {report.diagnosis} · PROBABILIDADE DE FALHA {report.failure_probability}")
        self.status.setText("  SAÚDE · MEDIDA OPERACIONAL/ESTATÍSTICA · NÃO É PROBABILIDADE")

    def _report_rows(self) -> list[dict]:
        rows = self.history.query(limit=self.services.settings.analysis.export_limit)
        if rows:
            return rows
        return [{
            "status": "SEM DADOS", "equipamento": "NÃO CONECTADO",
            "ipro": "AGUARDANDO MAPA OFICIAL", "vx_1050e": "AGUARDANDO MAPA OFICIAL",
        }]

    def _export_report(self, format_name: str) -> None:
        rows = self._report_rows()
        if format_name == "PDF":
            target = self.reports.pdf("CNCold Industrial Diagnostics", rows)
        elif format_name == "CSV":
            target = self.reports.csv(rows)
        else:
            target = self.reports.json(rows)
        self.evidence.append("relatorios", {"event": "REPORT_EXPORTED", "format": format_name, "path": str(target)})
        self.report_status.setText(f"Gerado: {target}")
        self.card_evidence.update_value(str(self.evidence.count()))

    def closeEvent(self, event) -> None:
        if self.rs485.active:
            self.rs485.stop()
        event.accept()


def run(project_root: Path) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("CNCold iPro Professional Bench")
    window = MainWindow(project_root)
    window.show()
    return app.exec()
