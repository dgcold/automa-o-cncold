from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .communication import Rs485SimulatorService, TcpReadOnlyService
from .core import BenchState, ConnectionState, OperationMode
from .drivers import build_default_registry
from .electrical import ElectricalMeasurementService
from .evidence import EvidenceStore
from .history_store import PersistentHistory
from .mapping import ModbusMapRepository
from .reports import ReportExporter
from .scenarios import Scenario, ScenarioManager
from .test_manager import BenchTest, TestManager, TestResult


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
        for start, end in zip(points, points[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])


class MainWindow(QMainWindow):
    NAVIGATION = (
        "Dashboard", "Sensores", "I/O", "Medição Elétrica", "Modbus", "Mapa",
        "Cenários", "Testes", "Gráficos", "Histórico", "Evidências",
        "Diagnóstico", "Relatórios",
    )

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.state = BenchState()
        self.evidence = EvidenceStore(project_root / "evidencias")
        self.history = PersistentHistory(project_root / "dados" / "historico.sqlite3")
        self.electrical = ElectricalMeasurementService(self.history)
        self.scenario_manager = ScenarioManager(self.evidence)
        self.reports = ReportExporter(project_root / "relatorios")
        self.controllers = build_default_registry(project_root)
        self.active_controller = self.controllers.get("ipro")
        self.map_repository = ModbusMapRepository(project_root / "config" / "modbus_map.json", project_root / "config" / "map_history")
        self.test_manager = TestManager(self.evidence)
        self.tcp = TcpReadOnlyService(self.state.ipro_ip, self.state.tcp_port)
        self.rs485 = Rs485SimulatorService(logger=self._rs485_log)
        self.probe_thread: TcpProbeThread | None = None
        self.setWindowTitle("CNCold iPro Professional Bench")
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
        side_layout.addWidget(QLabel("v0.2.0 · ETAPA A", objectName="subtitle"))
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
        self.pages.addWidget(self._trends_page())
        self.pages.addWidget(self._history_page())
        self.pages.addWidget(self._evidence_page())
        self.pages.addWidget(self._diagnostics_page())
        self.pages.addWidget(self._reports_page())
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

    def _dashboard(self) -> QWidget:
        page, layout = self._page()
        intro = QLabel("Visão operacional da bancada")
        intro.setStyleSheet("font-size:16px;font-weight:600")
        layout.addWidget(intro)
        grid = QGridLayout()
        self.card_ipro = StatusCard("iPro", "OFFLINE", "192.168.0.250 · Unit 1 · v107 preservada")
        self.card_controller = self.card_ipro
        self.card_tcp = StatusCard("Modbus TCP", "DESCONECTADO", "Porta 502 · FC03/FC04 somente leitura")
        self.card_rs485 = StatusCard("RS485", "INATIVO", "COM8 · 9600 · 8N2 · não aberta")
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
        tcp = StatusCard("Modbus TCP / iPro real", "SOMENTE LEITURA", "192.168.0.250:502 · Unit 1 · whitelist FC03/FC04")
        tcp_layout = tcp.layout()
        self.tcp_button = QPushButton("Testar conexão TCP")
        self.tcp_button.clicked.connect(self._probe_tcp)
        tcp_layout.addWidget(self.tcp_button)
        layout.addWidget(tcp)
        rs = StatusCard("Modbus RTU / simulador", "PARADO", "COM8 · 9600 · 8 bits · N · 2 stop bits")
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
        row.addWidget(self.scenario_name, 1)
        row.addWidget(create)
        layout.addLayout(row)
        self.scenarios_table = QTableWidget(0, 4)
        self.scenarios_table.setHorizontalHeaderLabels(("ID", "CENÁRIO", "TIPO", "STATUS"))
        self.scenarios_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.scenarios_table)
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
        layout.addWidget(QLabel("Gráficos", objectName="title"))
        self.sensor_chart = TrendChart("Sensores e processo")
        self.electrical_chart = TrendChart("Corrente total / compressor / L1 / L2 / L3")
        layout.addWidget(self.sensor_chart)
        layout.addWidget(self.electrical_chart)
        return page

    def _history_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(QLabel("Histórico persistente", objectName="title"))
        layout.addWidget(QLabel(f"SQLite append-only · {self.history.count()} amostras", objectName="muted"))
        rows = self.history.query(limit=250)
        table = QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels(("DATA/HORA", "CANAL", "VALOR", "UNIDADE", "QUALIDADE", "FONTE", "CONEXÃO"))
        for row, item in enumerate(rows):
            values = (item["timestamp"], item["channel_id"], item["value"] if item["value"] is not None else "SEM DADOS", item["unit"], item["quality"], item["source"], "SIM" if item["connected"] else "NÃO")
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
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
        layout.addWidget(QLabel("Central de diagnóstico", objectName="title"))
        for title, value in (("Proteção contra escrita", "ATIVA · FC03/FC04 apenas"), ("TCP", "OFFLINE · teste manual disponível"), ("RS485", "INATIVO · COM8 não aberta"), ("Mapa", "AGUARDANDO MAPA MODBUS OFICIAL")):
            layout.addWidget(StatusCard(title, value, "Nenhuma ação automática configurada"))
        layout.addStretch()
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
        answer = QMessageBox.question(self, "Abrir COM8", "Iniciar o respondedor RS485 em COM8 / 9600 / 8N2?\nA porta não é aberta até esta confirmação.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.rs485.start()
        self.state.rs485_state = ConnectionState.CONNECTING
        self.rs_start.setEnabled(False)
        self.rs_stop.setEnabled(True)
        self.card_rs485.update_value("INICIANDO", "COM8 · 9600 · 8N2")

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
        except Exception as error:
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

    def _report_rows(self) -> list[dict]:
        rows = self.history.query(limit=1000)
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
