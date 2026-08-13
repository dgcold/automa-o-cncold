import math
import os
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from collections import deque
from datetime import datetime

from serial.tools import list_ports

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from conversao_sinais import calcular_saida_canal
from gerador_sinais import GeradorRefrigeracao, Historico
from janela_modbus import JanelaModbus
from painel_simulador_ipro import PainelSimuladorIPro
from refrigerantes import REFRIGERANTES, coolprop_disponivel
from config_modbus import carregar
from estado_maquina import (
    EstadoMaquina,
    calcular_estado_maquina,
    controles_simulador_habilitados,
    deve_usar_dados_reais,
)
from ipro_map import (
    QUALIDADE_DESATUALIZADA,
    QUALIDADE_PROVISORIA,
    QUALIDADE_VALIDA,
)
from modbus_rs485 import (
    COMUNICACAO_DESCONECTADO,
    COMUNICACAO_OK,
    COMUNICACAO_PARCIAL,
)


INTERVALO_ATUALIZACAO_MS = 1000
MAX_PONTOS_GRAFICO = 120
ARQUIVO_HISTORICO = "historico_gerador_refrigeracao.csv"


class CartaoStatus(QFrame):
    def __init__(self, titulo: str, subtitulo: str, cor: str) -> None:
        super().__init__()
        self.setObjectName("cartaoStatus")
        self.setMinimumWidth(180)
        self.setMinimumHeight(62)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(0)

        self.titulo = QLabel()
        self.titulo.setAlignment(Qt.AlignCenter)
        self.titulo.setTextFormat(Qt.RichText)

        self.subtitulo = QLabel(subtitulo)
        self.subtitulo.setAlignment(Qt.AlignCenter)
        self.subtitulo.setObjectName("subtituloStatus")

        layout.addWidget(self.titulo)
        layout.addWidget(self.subtitulo)

        self.atualizar(titulo, cor)

    def atualizar(self, titulo: str, cor: str) -> None:
        self.titulo.setText(
            f"<span style='color:{cor}; font-size:16px; font-weight:900;'>● {titulo}</span>"
        )


class GraficoTendencias(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.camara = deque(maxlen=MAX_PONTOS_GRAFICO)
        self.evaporador = deque(maxlen=MAX_PONTOS_GRAFICO)

        self.setMinimumHeight(255)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def adicionar(self, camara: float, evaporador: float) -> None:
        self.camara.append(camara)
        self.evaporador.append(evaporador)
        self.update()

    def limpar(self) -> None:
        self.camara.clear()
        self.evaporador.clear()
        self.update()

    def paintEvent(self, event) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        margem_esquerda = 50
        margem_direita = 16
        margem_superior = 22
        margem_inferior = 48

        area = QRectF(
            margem_esquerda,
            margem_superior,
            self.width() - margem_esquerda - margem_direita,
            self.height() - margem_superior - margem_inferior,
        )

        painter.setPen(QPen(QColor("#dce3eb"), 1))

        for indice in range(7):
            y = area.top() + indice * area.height() / 6
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))

        for indice in range(5):
            x = area.left() + indice * area.width() / 4
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))

        painter.setPen(QPen(QColor("#a5b0bd"), 1))
        painter.drawRect(area)

        todos = list(self.camara) + list(self.evaporador)

        minimo = -30.0
        maximo = 30.0

        if todos:
            minimo = min(minimo, min(todos) - 2.0)
            maximo = max(maximo, max(todos) + 2.0)

        intervalo = maximo - minimo

        def desenhar(serie, cor: str) -> None:
            if len(serie) < 2:
                return

            painter.setPen(QPen(QColor(cor), 2.5))
            pontos = []
            divisor = max(1, MAX_PONTOS_GRAFICO - 1)

            for indice, valor in enumerate(serie):
                x = area.left() + indice * area.width() / divisor
                y = area.bottom() - (valor - minimo) * area.height() / intervalo
                pontos.append(QPointF(x, y))

            for indice in range(len(pontos) - 1):
                painter.drawLine(pontos[indice], pontos[indice + 1])

        desenhar(list(self.camara), "#126cc1")
        desenhar(list(self.evaporador), "#8a42bd")

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#2f3b49"))

        for valor in [30, 20, 10, 0, -10, -20, -30]:
            y = area.bottom() - (valor - minimo) * area.height() / intervalo
            if area.top() <= y <= area.bottom():
                painter.drawText(5, int(y) + 4, f"{valor}")

        painter.drawText(2, 16, "°C")
        painter.drawText(int(area.left()), self.height() - 12, "-120s")
        painter.drawText(int(area.left() + area.width() * 0.25), self.height() - 12, "-90s")
        painter.drawText(int(area.left() + area.width() * 0.50), self.height() - 12, "-60s")
        painter.drawText(int(area.left() + area.width() * 0.75), self.height() - 12, "-30s")
        painter.drawText(int(area.right() - 15), self.height() - 12, "0s")

        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor("#126cc1"))
        painter.drawText(int(area.left() + 60), self.height() - 12, "━━ Câmara")

        painter.setPen(QColor("#8a42bd"))
        painter.drawText(int(area.left() + 190), self.height() - 12, "━━ Evaporador")


class SinoticoFinal(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.temperatura_camara = 20.0
        self.temperatura_evaporador = 15.0
        self.pressao_succao = 90.0
        self.pressao_descarga = 100.0
        self.modo = 1
        self.nome_modo = "MÁQUINA PARADA"
        self.em_alarme_automatico = False
        self.estado_maquina: EstadoMaquina | None = None

        self.setMinimumHeight(420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def atualizar(
        self,
        gerador: GeradorRefrigeracao,
        estado_maquina: EstadoMaquina,
    ) -> None:
        self.temperatura_camara = gerador.camara.valor
        self.temperatura_evaporador = gerador.evaporador.valor
        self.pressao_succao = gerador.succao.valor
        self.pressao_descarga = gerador.descarga.valor
        self.modo = estado_maquina.modo
        self.nome_modo = estado_maquina.nome_modo
        self.em_alarme_automatico = estado_maquina.em_alarme
        self.estado_maquina = estado_maquina
        self.update()

    @staticmethod
    def _seta(
        painter: QPainter,
        inicio: QPointF,
        fim: QPointF,
        cor: str,
        largura: int = 4,
    ) -> None:
        painter.setPen(QPen(QColor(cor), largura))
        painter.drawLine(inicio, fim)

        painter.setBrush(QColor(cor))
        painter.setPen(Qt.NoPen)

        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        comprimento = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux = dx / comprimento
        uy = dy / comprimento

        ponta_1 = QPointF(
            fim.x() - 13 * ux + 7 * uy,
            fim.y() - 13 * uy - 7 * ux,
        )
        ponta_2 = QPointF(
            fim.x() - 13 * ux - 7 * uy,
            fim.y() - 13 * uy + 7 * ux,
        )

        painter.drawPolygon([fim, ponta_1, ponta_2])

    @staticmethod
    def _caixa_valor(
        painter: QPainter,
        rect: QRectF,
        titulo: str,
        valor: str,
        cor: str,
    ) -> None:
        painter.setPen(QPen(QColor("#c8d1dc"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 7, 7)

        painter.setPen(QColor(cor))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(
            QRectF(rect.left(), rect.top() + 5, rect.width(), 18),
            Qt.AlignCenter,
            titulo,
        )

        painter.setFont(QFont("Segoe UI", 14, QFont.Bold))
        painter.drawText(
            QRectF(rect.left(), rect.top() + 24, rect.width(), 30),
            Qt.AlignCenter,
            valor,
        )

    def paintEvent(self, event) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        fundo = QLinearGradient(0, 0, 0, self.height())
        fundo.setColorAt(0, QColor("#ffffff"))
        fundo.setColorAt(1, QColor("#f5f9fd"))
        painter.fillRect(self.rect(), fundo)

        w = self.width()
        h = self.height()

        azul = "#126fc2"
        vermelho = "#cf2d24"
        amarelo = "#d28c00"
        azul_escuro = QColor("#17375e")

        # caixas de pressão superiores
        self._caixa_valor(
            painter,
            QRectF(w * 0.34, 20, w * 0.18, 62),
            "SUCÇÃO",
            f"{self.pressao_succao:.2f} PSI",
            azul,
        )
        self._caixa_valor(
            painter,
            QRectF(w * 0.61, 20, w * 0.18, 62),
            "DESCARGA",
            f"{self.pressao_descarga:.2f} PSI",
            vermelho,
        )

        # câmara
        camara = QRectF(18, 110, w * 0.23, h * 0.62)
        painter.setPen(QPen(azul_escuro, 3))
        painter.setBrush(QColor("#edf6ff"))
        painter.drawRoundedRect(camara, 8, 8)

        painter.setPen(azul_escuro)
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(
            QRectF(camara.left(), camara.top() + 14, camara.width(), 56),
            Qt.AlignCenter,
            "CÂMARA\nFRIGORÍFICA",
        )

        painter.setFont(QFont("Segoe UI", 24, QFont.Bold))
        painter.drawText(
            QRectF(camara.left(), camara.center().y() - 35, camara.width(), 70),
            Qt.AlignCenter,
            f"{self.temperatura_camara:.2f} °C",
        )

        painter.setPen(QPen(QColor("#7b8da1"), 2))
        painter.drawRoundedRect(
            QRectF(camara.right() - 24, camara.top() + 130, 9, 82),
            4,
            4,
        )

        painter.setPen(QColor("#3b79b8"))
        painter.setFont(QFont("Segoe UI", 30))
        painter.drawText(
            QRectF(camara.left(), camara.bottom() - 70, camara.width(), 55),
            Qt.AlignCenter,
            "❄",
        )

        # evaporador
        evaporador = QRectF(w * 0.30, h * 0.37, w * 0.18, h * 0.29)
        painter.setPen(QPen(QColor(azul), 2))
        painter.setBrush(QColor("#f0f8ff"))
        painter.drawRoundedRect(evaporador, 8, 8)

        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(
            QRectF(evaporador.left(), evaporador.top() + 9, evaporador.width(), 24),
            Qt.AlignCenter,
            "EVAPORADOR",
        )

        # Serpentina mais compacta para não sobrepor a temperatura.
        for indice in range(4):
            y = evaporador.top() + 46 + indice * 14

            painter.drawRoundedRect(
                QRectF(
                    evaporador.left() + 25,
                    y,
                    evaporador.width() * 0.55,
                    6,
                ),
                3,
                3,
            )

        # Temperatura posicionada abaixo da serpentina.
        painter.setPen(QColor(azul))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        painter.drawText(
            QRectF(
                evaporador.left() + 8,
                evaporador.bottom() - 34,
                evaporador.width() - 16,
                26,
            ),
            Qt.AlignCenter,
            f"{self.temperatura_evaporador:.2f} °C",
        )

        # compressor
        compressor = QRectF(w * 0.55, h * 0.37, w * 0.16, h * 0.29)

        estado_unico = self.estado_maquina

        estado = (
            estado_unico.estado_compressor
            if estado_unico is not None
            else "PARADO"
        )

        if estado == "SEM COMUNICAÇÃO":
            cor_compressor = QColor("#7a8694")
        elif estado == "COMUNICAÇÃO PARCIAL":
            cor_compressor = QColor("#c17800")
        elif estado == "FALHA":
            cor_compressor = QColor("#d9534f")
        elif estado == "RESFRIANDO":
            cor_compressor = QColor("#62be6d")
        elif estado == "DEGELO":
            cor_compressor = QColor("#f0ae43")
        else:
            cor_compressor = QColor("#d9dfe6")
            estado = "PARADO"

        painter.setPen(QPen(QColor("#3a4858"), 3))
        painter.setBrush(cor_compressor)
        painter.drawRoundedRect(compressor, 14, 14)

        painter.setPen(QColor("#182736"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(
            QRectF(compressor.left(), compressor.top() + 16, compressor.width(), 28),
            Qt.AlignCenter,
            "COMPRESSOR",
        )

        painter.setFont(QFont("Segoe UI", 15, QFont.Bold))
        painter.drawText(
            QRectF(compressor.left(), compressor.bottom() - 52, compressor.width(), 34),
            Qt.AlignCenter,
            estado,
        )

        # condensador
        condensador = QRectF(w * 0.80, h * 0.37, w * 0.16, h * 0.29)
        painter.setPen(QPen(QColor(vermelho), 2))
        painter.setBrush(QColor("#fff2f0"))
        painter.drawRoundedRect(condensador, 8, 8)

        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(
            QRectF(condensador.left(), condensador.top() + 9, condensador.width(), 24),
            Qt.AlignCenter,
            "CONDENSADOR",
        )

        for indice in range(5):
            y = condensador.top() + 48 + indice * 16
            painter.drawRoundedRect(
                QRectF(condensador.left() + 25, y, condensador.width() * 0.55, 7),
                4,
                4,
            )

        # circuito superior
        self._seta(
            painter,
            QPointF(camara.right(), camara.top() + 95),
            QPointF(evaporador.left(), evaporador.center().y()),
            azul,
        )
        self._seta(
            painter,
            QPointF(evaporador.right(), evaporador.center().y()),
            QPointF(compressor.left(), compressor.center().y()),
            azul,
        )
        self._seta(
            painter,
            QPointF(compressor.right(), compressor.center().y()),
            QPointF(condensador.left(), condensador.center().y()),
            vermelho,
        )

        # circuito amarelo inferior
        painter.setPen(QPen(QColor(amarelo), 4))
        y_inferior = h * 0.76
        painter.drawLine(
            QPointF(condensador.center().x(), condensador.bottom()),
            QPointF(condensador.center().x(), y_inferior),
        )
        painter.drawLine(
            QPointF(condensador.center().x(), y_inferior),
            QPointF(w * 0.50, y_inferior),
        )

        separador = QRectF(w * 0.43, y_inferior - 20, 40, 52)
        painter.setPen(QPen(QColor("#8f6400"), 2))
        painter.setBrush(QColor("#f3bd45"))
        painter.drawRoundedRect(separador, 7, 7)

        painter.setPen(QColor("#805900"))
        painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
        painter.drawText(separador, Qt.AlignCenter, "◊")

        painter.setPen(QPen(QColor(amarelo), 4))
        painter.drawLine(
            QPointF(separador.left(), separador.center().y()),
            QPointF(w * 0.29, separador.center().y()),
        )
        painter.drawLine(
            QPointF(w * 0.29, separador.center().y()),
            QPointF(w * 0.29, camara.bottom() - 40),
        )
        self._seta(
            painter,
            QPointF(w * 0.29, camara.bottom() - 40),
            QPointF(camara.right() - 6, camara.bottom() - 40),
            amarelo,
        )

        # modo atual
        modo_rect = QRectF(18, h - 48, w * 0.50, 34)
        painter.setPen(QPen(QColor("#89b3df"), 1))
        painter.setBrush(QColor("#edf6ff"))
        painter.drawRoundedRect(modo_rect, 5, 5)

        painter.setPen(QColor("#153a66"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(modo_rect, Qt.AlignCenter, f"MODO ATUAL: {self.nome_modo}")


class JanelaFinal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CNCold Digital Twin iPro")
        self.resize(1520, 930)
        self.setMinimumSize(1280, 790)

        self.gerador = GeradorRefrigeracao()
        self.historico = Historico()

        self.contador_historico = 0
        self.pacotes_enviados = 0
        self.janela_modbus = None
        self.painel_simulador_ipro = None
        self.ultimo_dados_ipro: dict[str, object] = {}
        self.comunicacao_ipro = COMUNICACAO_OK
        self.possui_dados_reais = False
        self.estado_maquina = calcular_estado_maquina(self.gerador)

        # Fonte escolhida diretamente na interface:
        # SIMULADO, REAL ou AUTO.
        self.modo_fonte = "SIMULADO"
        self.ultimo_teste_auto = 0.0
        self.intervalo_teste_auto = 5.0

        # Comunicação AUTO em segundo plano para não travar a interface.
        self.executor_modbus = ThreadPoolExecutor(max_workers=1)
        self.future_auto: Future | None = None

        self._aplicar_estilo()
        self._montar_interface()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._atualizar)
        self.timer.start(INTERVALO_ATUALIZACAO_MS)

        self._atualizar()

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #e9eef4;
            }

            QWidget {
                font-family: "Segoe UI";
                color: #172b3f;
            }

            QGroupBox {
                background: #ffffff;
                border: 1px solid #d1dae4;
                border-radius: 10px;
                margin-top: 16px;
                padding-top: 10px;
                font-size: 13px;
                font-weight: 900;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #234e73;
                background: #ffffff;
                letter-spacing: 1px;
            }

            QPushButton {
                background: #f8fafc;
                border: 1px solid #d1dae5;
                border-radius: 8px;
                padding: 9px 11px;
                font-size: 12px;
                font-weight: 600;
                text-align: left;
            }

            QPushButton:hover {
                background: #edf5fc;
                border-color: #4385bb;
            }

            QPushButton:pressed {
                background: #deedff;
            }

            QPushButton:disabled {
                background: #f2f4f7;
                border-color: #e1e6ec;
                color: #9aa6b2;
            }

            QPushButton#botaoModo {
                background: #f5f9fc;
                border-left: 4px solid #2176ae;
                color: #173b58;
            }

            QPushButton#botaoAjuste {
                background: #f7f9fb;
                border-left: 4px solid #7b8b9d;
                color: #30475b;
            }

            QPushButton#botaoEncerrar {
                background: #fff7f7;
                border-left: 4px solid #b94141;
                color: #8f2929;
            }

            QComboBox, QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #cbd6e2;
                border-radius: 7px;
                min-height: 30px;
                padding: 2px 8px;
                font-weight: 700;
            }

            QComboBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #4b91cc;
            }

            QCheckBox {
                spacing: 8px;
                font-weight: 700;
                padding: 4px;
            }

            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #d7e0e9;
                border-radius: 8px;
                top: -1px;
            }

            QTabBar::tab {
                background: #edf3f8;
                color: #526477;
                border: 1px solid #d7e0e9;
                padding: 7px 12px;
                font-weight: 700;
            }

            QTabBar::tab:selected {
                background: #ffffff;
                color: #1767a5;
                border-bottom-color: #ffffff;
                border-top: 3px solid #2176ae;
            }

            QTableWidget {
                background: #ffffff;
                border: none;
                gridline-color: #dce4ed;
                alternate-background-color: #f6f8fb;
                font-size: 12px;
                border-radius: 8px;
            }

            QHeaderView::section {
                background: #173b5e;
                color: #ffffff;
                padding: 9px;
                border: 1px solid #d3dce7;
                font-weight: 900;
            }

            #cabecalho {
                background: #123654;
                border: 1px solid #123654;
                border-radius: 12px;
            }

            #cartaoStatus {
                background: #ffffff;
                border: 1px solid #d8e1e9;
                border-radius: 10px;
            }

            #subtituloStatus {
                color: #5d6d7d;
                font-size: 11px;
            }

            #rodape {
                background: #f8fafc;
                border: 1px solid #d1dae4;
                border-radius: 10px;
            }
            """
        )

    def _montar_interface(self) -> None:
        raiz = QWidget()
        self.setCentralWidget(raiz)

        layout_principal = QVBoxLayout(raiz)
        layout_principal.setContentsMargins(12, 12, 12, 10)
        layout_principal.setSpacing(10)

        layout_principal.addWidget(self._criar_cabecalho())

        superior = QHBoxLayout()
        superior.setSpacing(10)

        grupo_sinotico = QGroupBox("SINÓTICO DO PROCESSO")
        layout_sinotico = QVBoxLayout(grupo_sinotico)
        layout_sinotico.setContentsMargins(8, 8, 8, 8)

        self.sinotico = SinoticoFinal()
        layout_sinotico.addWidget(self.sinotico)
        superior.addWidget(grupo_sinotico, 5)

        grupo_canais = QGroupBox("CANAIS ANALÓGICOS")
        layout_canais = QVBoxLayout(grupo_canais)
        layout_canais.setContentsMargins(8, 8, 8, 8)

        self.tabela = self._criar_tabela()
        layout_canais.addWidget(self.tabela)
        superior.addWidget(grupo_canais, 5)

        layout_principal.addLayout(superior, 6)

        inferior = QHBoxLayout()
        inferior.setSpacing(10)

        inferior.addWidget(self._criar_comandos(), 4)
        inferior.addWidget(self._criar_alarmes(), 3)
        inferior.addWidget(self._criar_informacoes(), 4)

        layout_principal.addLayout(inferior, 4)
        layout_principal.addWidget(self._criar_rodape())

    def _criar_cabecalho(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("cabecalho")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(14)

        logo = QLabel("CNCOLD")
        logo.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 25px;
                font-weight: 900;
                letter-spacing: 2px;
                border: none;
            }
            """
        )

        titulo = QLabel("DIGITAL TWIN iPro")
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: 900;
                border: none;
            }
            """
        )

        subtitulo = QLabel("Supervisão, simulação e diagnóstico de refrigeração")
        subtitulo.setAlignment(Qt.AlignCenter)
        subtitulo.setStyleSheet(
            "color:#b9ccdc; font-size:11px; font-weight:600; border:none;"
        )
        bloco_titulo = QWidget()
        layout_titulo = QVBoxLayout(bloco_titulo)
        layout_titulo.setContentsMargins(0, 0, 0, 0)
        layout_titulo.setSpacing(0)
        layout_titulo.addWidget(titulo)
        layout_titulo.addWidget(subtitulo)

        bloco_fonte = QWidget()
        layout_fonte = QVBoxLayout(bloco_fonte)
        layout_fonte.setContentsMargins(4, 0, 4, 0)
        layout_fonte.setSpacing(2)

        legenda_fonte = QLabel("FONTE DOS DADOS")
        legenda_fonte.setAlignment(Qt.AlignCenter)
        legenda_fonte.setStyleSheet(
            "font-size:9px; font-weight:800; color:#b9ccdc; letter-spacing:1px;"
        )

        self.combo_fonte = QComboBox()
        self.combo_fonte.addItems(["SIMULADO", "REAL", "AUTO"])
        self.combo_fonte.setCurrentText("SIMULADO")
        self.combo_fonte.setMinimumWidth(125)
        self.combo_fonte.setStyleSheet(
            "QComboBox { background:#ffffff; color:#173b58; font-weight:800; }"
        )
        self.combo_fonte.currentTextChanged.connect(
            self._alterar_fonte_dados
        )

        layout_fonte.addWidget(legenda_fonte)
        layout_fonte.addWidget(self.combo_fonte)

        self.status_execucao = CartaoStatus("ATIVA", "Execução", "#14913c")
        self.status_modbus = CartaoStatus(
            "SIMULADO",
            "Comunicação RS485",
            "#c17800",
        )

        layout.addWidget(logo, 2)
        layout.addWidget(bloco_titulo, 5)
        layout.addWidget(bloco_fonte, 1)
        layout.addWidget(self.status_execucao, 1)
        layout.addWidget(self.status_modbus, 2)

        return frame

    def _criar_tabela(self) -> QTableWidget:
        tabela = QTableWidget(8, 7)
        tabela.setHorizontalHeaderLabels(
            ["Canal", "Variável", "Valor", "Sinal", "Registro", "End.", "Estado"]
        )
        tabela.verticalHeader().setVisible(False)
        tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        tabela.setSelectionMode(QTableWidget.NoSelection)
        tabela.setAlternatingRowColors(True)

        header = tabela.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        for linha in range(8):
            tabela.setRowHeight(linha, 38)

        return tabela

    def _criar_comandos(self) -> QWidget:
        grupo = QGroupBox("COMANDOS DO SIMULADOR")
        layout = QGridLayout(grupo)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setHorizontalSpacing(9)
        layout.setVerticalSpacing(6)

        titulo_modos = QLabel("MODOS DE OPERAÇÃO")
        titulo_modos.setStyleSheet("font-weight:900; color:#17609c;")

        titulo_ajustes = QLabel("CONTROLE")
        titulo_ajustes.setStyleSheet("font-weight:900; color:#17609c;")

        layout.addWidget(titulo_modos, 0, 0)
        layout.addWidget(titulo_ajustes, 0, 1)

        botoes_modo = [
            ("Máquina parada", lambda: self.gerador.selecionar_modo(1)),
            ("Resfriamento", lambda: self.gerador.selecionar_modo(2)),
            ("Degelo", lambda: self.gerador.selecionar_modo(3)),
            ("Simular falha", lambda: self.gerador.selecionar_modo(4)),
            ("Próxima falha", self.gerador.proxima_falha),
        ]

        botoes_ajuste = [
            ("Aumentar agressividade", self.gerador.aumentar_agressividade),
            ("Reduzir agressividade", self.gerador.diminuir_agressividade),
            ("Pausar simulação", self._alternar_pausa),
            ("Restaurar simulação", self._resetar),
            ("Encerrar aplicação", self.close),
        ]

        self.botoes_simulador = []

        for linha, (texto, comando) in enumerate(botoes_modo, start=1):
            botao = QPushButton(texto)
            botao.setObjectName("botaoModo")
            botao.clicked.connect(comando)
            self.botoes_simulador.append(botao)
            layout.addWidget(botao, linha, 0)

        for linha, (texto, comando) in enumerate(botoes_ajuste, start=1):
            botao = QPushButton(texto)
            botao.setObjectName(
                "botaoEncerrar" if "Encerrar" in texto else "botaoAjuste"
            )
            botao.clicked.connect(comando)

            if "Pausar" in texto:
                self.botao_pausa = botao

            if "Encerrar" not in texto:
                self.botoes_simulador.append(botao)

            layout.addWidget(botao, linha, 1)

        return grupo

    def _criar_alarmes(self) -> QWidget:
        grupo = QGroupBox("ALARMES")
        layout = QVBoxLayout(grupo)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(4)

        self.labels_alarmes = []

        nomes = [
            "Alta temperatura da câmara",
            "Alta pressão de descarga",
            "Alta temperatura de descarga",
            "Baixa pressão de sucção",
            "Falha de sensor",
            "Comunicação perdida",
        ]

        for nome in nomes:
            label = QLabel(f"●  {nome}")
            label.setStyleSheet(
                """
                QLabel {
                    color: #6e7784;
                    font-size: 12px;
                    padding: 5px;
                }
                """
            )
            layout.addWidget(label)
            self.labels_alarmes.append(label)

        self.label_resumo_alarme = QLabel("SEM ALARMES")
        self.label_resumo_alarme.setAlignment(Qt.AlignCenter)
        self.label_resumo_alarme.setStyleSheet(
            """
            QLabel {
                background:#ffffff;
                border:1px solid #cbd5e1;
                border-radius:6px;
                color:#16853a;
                font-size:16px;
                font-weight:900;
                padding:14px;
            }
            """
        )

        layout.addStretch()
        layout.addWidget(self.label_resumo_alarme)

        return grupo

    def _criar_informacoes(self) -> QWidget:
        grupo = QGroupBox("INFORMAÇÕES")
        layout_principal = QVBoxLayout(grupo)
        layout_principal.setContentsMargins(8, 8, 8, 8)

        abas = QTabWidget()
        layout_principal.addWidget(abas)

        # Aba Estado
        aba_estado = QWidget()
        layout_estado = QVBoxLayout(aba_estado)
        layout_estado.setContentsMargins(10, 10, 10, 10)
        layout_estado.setSpacing(6)

        label_refrigerante = QLabel("Refrigerante:")
        label_refrigerante.setStyleSheet(
            "font-size:12px; font-weight:800;"
        )
        layout_estado.addWidget(label_refrigerante)

        self.combo_refrigerante = QComboBox()
        self.combo_refrigerante.addItems(REFRIGERANTES.keys())
        self.combo_refrigerante.setCurrentText(
            self.gerador.refrigerante
        )
        self.combo_refrigerante.currentTextChanged.connect(
            self.gerador.selecionar_refrigerante
        )
        self.combo_refrigerante.setToolTip(
            (
                "Cálculo termodinâmico ativo com CoolProp."
                if coolprop_disponivel()
                else "Instale CoolProp para ativar os cálculos: "
                "python -m pip install CoolProp"
            )
        )
        layout_estado.addWidget(self.combo_refrigerante)

        self.info_modo = QLabel()
        self.info_agressividade = QLabel()
        self.info_execucao = QLabel()
        self.info_falha = QLabel()
        self.info_superaquecimento = QLabel()
        self.info_subresfriamento = QLabel()

        for label in [
            self.info_modo,
            self.info_agressividade,
            self.info_execucao,
            self.info_falha,
            self.info_superaquecimento,
            self.info_subresfriamento,
        ]:
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setStyleSheet(
                "font-size:11px; padding:3px 2px;"
            )
            layout_estado.addWidget(label)

        layout_estado.addStretch()
        abas.addTab(aba_estado, "Estado")

        # Aba Temperaturas
        aba_temperaturas = QWidget()
        layout_temperaturas = QVBoxLayout(aba_temperaturas)
        layout_temperaturas.setContentsMargins(10, 10, 10, 10)
        layout_temperaturas.setSpacing(8)

        self.check_modo_manual = QCheckBox(
            "Modo manual de temperaturas"
        )
        self.check_modo_manual.toggled.connect(
            self._alternar_modo_manual_temperaturas
        )
        layout_temperaturas.addWidget(self.check_modo_manual)

        self.spin_temperatura_camara = self._criar_spin_temperatura(
            -40.0, 50.0, self.gerador.camara.valor
        )
        self.spin_temperatura_camara.setMaximum(50.0)
        self.spin_temperatura_camara.setKeyboardTracking(False)
        self.spin_temperatura_evaporador = self._criar_spin_temperatura(
            -50.0, 60.0, self.gerador.evaporador.valor
        )
        self.spin_temperatura_succao = self._criar_spin_temperatura(
            -50.0, 80.0, self.gerador.temperatura_succao.valor
        )
        self.spin_temperatura_liquido = self._criar_spin_temperatura(
            -20.0, 100.0, self.gerador.temperatura_liquido.valor
        )
        self.spin_temperatura_descarga = self._criar_spin_temperatura(
            -20.0, 180.0, self.gerador.temperatura_descarga.valor
        )

        self.spin_pressao_succao = self._criar_spin_pressao(
            0.0, 150.0, self.gerador.succao.valor
        )
        self.spin_pressao_descarga = self._criar_spin_pressao(
            0.0, 500.0, self.gerador.descarga.valor
        )

        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Câmara:",
            self.spin_temperatura_camara,
            "camara",
        )
        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Evaporador:",
            self.spin_temperatura_evaporador,
            "evaporador",
        )
        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Linha de sucção:",
            self.spin_temperatura_succao,
            "linha_succao",
        )
        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Linha de líquido:",
            self.spin_temperatura_liquido,
            "linha_liquido",
        )
        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Descarga:",
            self.spin_temperatura_descarga,
            "temperatura_descarga",
        )

        separador_pressoes = QLabel("PRESSÕES MANUAIS")
        separador_pressoes.setStyleSheet(
            "font-size:11px; font-weight:900; color:#17609c; padding-top:6px;"
        )
        layout_temperaturas.addWidget(separador_pressoes)

        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Sucção:",
            self.spin_pressao_succao,
            "succao",
        )
        self._adicionar_ajuste_temperatura(
            layout_temperaturas,
            "Descarga:",
            self.spin_pressao_descarga,
            "descarga",
        )

        self._habilitar_controles_manuais(False)
        layout_temperaturas.addStretch()
        abas.addTab(aba_temperaturas, "Temperaturas")

        # Aba iPro: mostra todas as variáveis principais do mapa Modbus.
        aba_ipro = QWidget()
        layout_ipro = QGridLayout(aba_ipro)
        layout_ipro.setContentsMargins(10, 10, 10, 10)
        layout_ipro.setHorizontalSpacing(12)
        layout_ipro.setVerticalSpacing(5)

        self.labels_ipro: dict[str, QLabel] = {}
        campos_ipro = [
            ("temperatura_camara", "Temperatura câmara", "°C"),
            ("temperatura_evaporador", "Temperatura evaporador", "°C"),
            ("temperatura_externa", "Temperatura externa", "°C"),
            ("temperatura_insuflamento", "Temperatura insuflamento", "°C"),
            ("temperatura_descarga", "Temperatura descarga", "°C"),
            ("temperatura_succao", "Temperatura sucção", "°C"),
            ("temperatura_liquido", "Temperatura líquido", "°C"),
            ("temperatura_condensacao", "Temperatura condensação", "°C"),
            ("temperatura_evaporacao", "Temperatura evaporação", "°C"),
            ("pressao_succao_psi", "Pressão sucção", "PSI"),
            ("pressao_descarga_psi", "Pressão descarga", "PSI"),
            ("superaquecimento", "Superaquecimento", "°C"),
            ("subresfriamento", "Sub-resfriamento", "°C"),
            ("abertura_valvula", "Abertura válvula", "%"),
            ("capacidade_compressor", "Capacidade compressor", "%"),
            ("capacidade_condensador", "Capacidade condensador", "%"),
        ]

        for indice, (chave, titulo, unidade) in enumerate(campos_ipro):
            linha = indice // 2
            coluna = (indice % 2) * 2
            layout_ipro.addWidget(QLabel(f"{titulo}:"), linha, coluna)
            valor = QLabel(f"-- {unidade}")
            valor.setStyleSheet("font-weight:900; color:#126cc1;")
            layout_ipro.addWidget(valor, linha, coluna + 1)
            self.labels_ipro[chave] = valor

        linha_estados = (len(campos_ipro) + 1) // 2
        titulo_estados = QLabel("ESTADOS DO IPRO")
        titulo_estados.setStyleSheet(
            "font-size:11px; font-weight:900; color:#17609c; padding-top:6px;"
        )
        layout_ipro.addWidget(titulo_estados, linha_estados, 0, 1, 4)

        self.labels_ipro_status: dict[str, QLabel] = {}
        estados_ipro = [
            ("unidade", "Unidade"),
            ("compressor", "Compressor"),
            ("evaporador", "Evaporador"),
            ("condensador_1", "Condensador 1"),
            ("condensador_2", "Condensador 2"),
            ("degelo", "Degelo"),
            ("solenoide_liquido", "Solenóide líquido"),
        ]

        for indice, (chave, titulo) in enumerate(estados_ipro):
            linha = linha_estados + 1 + indice // 2
            coluna = (indice % 2) * 2
            layout_ipro.addWidget(QLabel(f"{titulo}:"), linha, coluna)
            estado = QLabel("OFF")
            estado.setStyleSheet("font-weight:900; color:#6e7784;")
            layout_ipro.addWidget(estado, linha, coluna + 1)
            self.labels_ipro_status[chave] = estado

        layout_ipro.setRowStretch(linha_estados + 6, 1)
        abas.addTab(aba_ipro, "iPro")

        # Aba Comunicação
        aba_comunicacao = QWidget()
        layout_comunicacao = QVBoxLayout(aba_comunicacao)
        layout_comunicacao.setContentsMargins(10, 10, 10, 10)
        layout_comunicacao.setSpacing(7)

        self.info_com_status = QLabel("Status: aguardando")
        self.info_com_porta = QLabel("Porta: --")
        self.info_com_baud = QLabel("Baud: --")
        self.info_com_slave = QLabel("Slave ID: --")
        self.info_com_pacotes = QLabel("Pacotes enviados: 0")
        self.info_com_ultimo = QLabel("Último envio: --:--:--")
        self.info_com_erro = QLabel("Último erro: Nenhum")

        for label in [
            self.info_com_status,
            self.info_com_porta,
            self.info_com_baud,
            self.info_com_slave,
            self.info_com_pacotes,
            self.info_com_ultimo,
            self.info_com_erro,
        ]:
            label.setStyleSheet(
                "font-size:11px; padding:4px 2px;"
            )
            layout_comunicacao.addWidget(label)

        botao_configurar = QPushButton("Configurar Modbus")
        botao_configurar.clicked.connect(
            self._abrir_janela_modbus
        )
        layout_comunicacao.addWidget(botao_configurar)
        layout_comunicacao.addStretch()

        abas.addTab(aba_comunicacao, "Comunicação")

        return grupo

    @staticmethod
    def _criar_spin_temperatura(
        minimo: float,
        maximo: float,
        valor: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimo, maximo)
        spin.setDecimals(2)
        spin.setSingleStep(0.5)
        spin.setSuffix(" °C")
        spin.setKeyboardTracking(False)
        spin.setValue(valor)
        return spin

    @staticmethod
    def _criar_spin_pressao(
        minimo: float,
        maximo: float,
        valor: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimo, maximo)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setSuffix(" PSI")
        spin.setKeyboardTracking(False)
        spin.setValue(valor)
        return spin

    def _adicionar_ajuste_temperatura(
        self,
        layout: QVBoxLayout,
        titulo: str,
        spin: QDoubleSpinBox,
        nome: str,
    ) -> None:
        linha = QHBoxLayout()
        label = QLabel(titulo)
        label.setMinimumWidth(105)
        linha.addWidget(label)
        linha.addWidget(spin)
        layout.addLayout(linha)

        spin.editingFinished.connect(
            lambda campo=spin, chave=nome: (
                self.gerador.definir_temperatura_manual(
                    chave,
                    campo.value(),
                )
            )
        )

    def _habilitar_controles_manuais(self, habilitar: bool) -> None:
        habilitar = (
            habilitar
            and controles_simulador_habilitados(self.modo_fonte)
        )
        for spin in [
            self.spin_temperatura_camara,
            self.spin_temperatura_evaporador,
            self.spin_temperatura_succao,
            self.spin_temperatura_liquido,
            self.spin_temperatura_descarga,
            self.spin_pressao_succao,
            self.spin_pressao_descarga,
        ]:
            spin.setEnabled(habilitar)

    def _alternar_modo_manual_temperaturas(self, ativo: bool) -> None:
        self.gerador.ativar_modo_manual_temperaturas(ativo)
        self._habilitar_controles_manuais(ativo)

        if ativo:
            self.spin_temperatura_camara.setValue(
                self.gerador.camara.valor
            )
            self.spin_temperatura_evaporador.setValue(
                self.gerador.evaporador.valor
            )
            self.spin_temperatura_succao.setValue(
                self.gerador.temperatura_succao.valor
            )
            self.spin_temperatura_liquido.setValue(
                self.gerador.temperatura_liquido.valor
            )
            self.spin_temperatura_descarga.setValue(
                self.gerador.temperatura_descarga.valor
            )
            self.spin_pressao_succao.setValue(
                self.gerador.succao.valor
            )
            self.spin_pressao_descarga.setValue(
                self.gerador.descarga.valor
            )

    def _criar_rodape(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("rodape")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 5, 12, 5)

        self.rodape_modbus = QLabel("RS485/Modbus\nMODO SIMULADO")
        self.rodape_com = QLabel("COM:\nSIMULADO")
        self.rodape_baud = QLabel("BAUD:\n9600")
        self.rodape_slave = QLabel("SLAVE ID:\n1")
        self.rodape_ultimo = QLabel("ÚLTIMA LEITURA:\n--:--:--")
        self.rodape_pacotes = QLabel("LEITURAS/LIGAÇÕES:\n0")
        self.rodape_historico = QLabel(f"HISTÓRICO:\n{ARQUIVO_HISTORICO}")

        for label in [
            self.rodape_modbus,
            self.rodape_com,
            self.rodape_baud,
            self.rodape_slave,
            self.rodape_ultimo,
            self.rodape_pacotes,
            self.rodape_historico,
        ]:
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                """
                QLabel {
                    border:none;
                    font-size:10px;
                    font-weight:800;
                    padding:3px 8px;
                }
                """
            )
            layout.addWidget(label)

        botao_abrir = QPushButton("Abrir pasta")
        botao_abrir.setStyleSheet(
            """
            QPushButton {
                text-align:center;
                min-width:100px;
            }
            """
        )
        botao_abrir.clicked.connect(self._abrir_pasta_historico)
        layout.addWidget(botao_abrir)

        botao_modbus = QPushButton("Configurar Modbus")
        botao_modbus.setStyleSheet(
            """
            QPushButton {
                text-align:center;
                min-width:130px;
            }
            """
        )
        botao_modbus.clicked.connect(self._abrir_janela_modbus)
        layout.addWidget(botao_modbus)

        botao_slave = QPushButton("Simulador Slave 1/2")
        botao_slave.clicked.connect(self._abrir_simulador_ipro)
        layout.addWidget(botao_slave)

        return frame

    def _alternar_pausa(self) -> None:
        self.gerador.pausado = not self.gerador.pausado
        self.botao_pausa.setText(
            "Continuar simulação"
            if self.gerador.pausado
            else "Pausar simulação"
        )

    def _resetar(self) -> None:
        self.gerador.resetar()
        self.check_modo_manual.setChecked(False)
        self.botao_pausa.setText("Pausar simulação")

    @staticmethod
    def _abrir_pasta_historico() -> None:
        pasta = os.path.abspath(os.getcwd())
        os.startfile(pasta)

    def _obter_modbus(self):
        """Cria a janela Modbus somente quando ela for necessária."""
        if self.janela_modbus is None:
            self.janela_modbus = JanelaModbus()
            self.janela_modbus.destroyed.connect(
                lambda: setattr(self, "janela_modbus", None)
            )
        return self.janela_modbus.modbus

    def _alterar_fonte_dados(self, modo: str) -> None:
        """Alterna a fonte sem editar código ou arquivo JSON."""
        self.modo_fonte = str(modo).upper()
        self.ultimo_dados_ipro.clear()
        self.comunicacao_ipro = (
            COMUNICACAO_OK
            if self.modo_fonte == "SIMULADO"
            else COMUNICACAO_DESCONECTADO
        )
        self.possui_dados_reais = False
        self._atualizar_controles_simulador()

        if self.modo_fonte == "SIMULADO":
            if self.janela_modbus is not None:
                self.janela_modbus.modbus.desconectar()
                self.janela_modbus.modbus.simulado = True

            self.status_modbus.atualizar(
                "SIMULADO",
                "#c17800",
            )
            return

        modbus = self._obter_modbus()
        modbus.desconectar()
        modbus.simulado = False

        if self.modo_fonte == "REAL":
            modbus.conectar()
        else:
            # AUTO tenta imediatamente e volta a tentar periodicamente.
            self.ultimo_teste_auto = 0.0

    def _atualizar_controles_simulador(self) -> None:
        habilitar = controles_simulador_habilitados(self.modo_fonte)
        for botao in getattr(self, "botoes_simulador", []):
            botao.setEnabled(habilitar)
        self.check_modo_manual.setEnabled(habilitar)
        if not habilitar:
            self.check_modo_manual.setChecked(False)
        self._habilitar_controles_manuais(
            habilitar and self.check_modo_manual.isChecked()
        )

    def _tentar_conectar_real(self, forcar: bool = False) -> bool:
        modbus = self._obter_modbus()
        modbus.simulado = False

        if modbus.conectado:
            return True

        agora = time.monotonic()

        if (
            not forcar
            and agora - self.ultimo_teste_auto < self.intervalo_teste_auto
        ):
            return False

        self.ultimo_teste_auto = agora
        return bool(modbus.conectar())

    def _abrir_janela_modbus(self) -> None:
        self._obter_modbus()

        self.janela_modbus.show()
        self.janela_modbus.raise_()
        self.janela_modbus.activateWindow()

    def _abrir_simulador_ipro(self) -> None:
        if self.painel_simulador_ipro is None:
            self.painel_simulador_ipro = PainelSimuladorIPro()
        self.painel_simulador_ipro.show()
        self.painel_simulador_ipro.raise_()
        self.painel_simulador_ipro.activateWindow()

    def _aplicar_leituras_ipro(self, dados: dict[str, object]) -> None:
        """Aplica as leituras reais do iPro ao modelo já usado pela interface."""
        self.ultimo_dados_ipro = dict(dados)
        self.comunicacao_ipro = str(
            dados.get("_comunicacao", COMUNICACAO_DESCONECTADO)
        )
        self.possui_dados_reais = True
        leituras = dados.get("_leituras", {})

        destinos = {
            "temperatura_camara": (self.gerador.camara, "°C"),
            "temperatura_evaporador": (self.gerador.evaporador, "°C"),
            "pressao_succao_bar": (self.gerador.succao, "PSI"),
            "pressao_descarga_bar": (self.gerador.descarga, "PSI"),
            "temperatura_succao": (self.gerador.temperatura_succao, "°C"),
            "temperatura_liquido": (self.gerador.temperatura_liquido, "°C"),
            "temperatura_descarga": (self.gerador.temperatura_descarga, "°C"),
        }
        canais_validos: set[str] = set()
        for chave, (canal, unidade_esperada) in destinos.items():
            leitura = leituras.get(chave, {})
            valor = leitura.get("valor")
            qualidade = leitura.get("qualidade")
            unidade = leitura.get("unidade_interface")
            if (
                valor is not None
                and qualidade in {QUALIDADE_VALIDA, QUALIDADE_PROVISORIA}
                and unidade == unidade_esperada
            ):
                canal.valor = float(valor)
                nome_operacional = (
                    chave.replace("_bar", "_psi")
                    if unidade_esperada == "PSI"
                    else chave
                )
                canais_validos.add(nome_operacional)

        # Estado visual principal baseado no controlador real.
        leitura_degelo = leituras.get("degelo", {})
        leitura_compressor = leituras.get("compressor", {})
        qualidade_digital_aceita = {QUALIDADE_VALIDA, QUALIDADE_PROVISORIA}
        if (
            leitura_degelo.get("qualidade") in qualidade_digital_aceita
            and leitura_degelo.get("valor") is True
        ):
            self.gerador.modo = 3
        elif (
            leitura_compressor.get("qualidade") in qualidade_digital_aceita
            and leitura_compressor.get("valor") is True
        ):
            self.gerador.modo = 2
        elif (
            leitura_compressor.get("qualidade") in qualidade_digital_aceita
            and leitura_compressor.get("valor") is False
        ):
            self.gerador.modo = 1

        # Leituras reais não passam pelos limites artificiais do simulador.
        self.gerador._avaliar_alarmes_automaticos(
            canais_validos,
            avaliar_limites_sensor=False,
        )

    def _tarefa_auto_modbus(self) -> dict[str, object] | None:
        """Tenta conectar e ler o iPro sem bloquear ou repetir erro de COM inválida."""
        modbus = self._obter_modbus()
        modbus.simulado = False

        # Só tenta abrir uma porta que realmente exista e não seja Bluetooth.
        porta_configurada = str(modbus.porta).upper()
        porta_encontrada = None

        for porta in list_ports.comports():
            if str(porta.device).upper() == porta_configurada:
                porta_encontrada = porta
                break

        if porta_encontrada is None:
            return None

        descricao = str(getattr(porta_encontrada, "description", "")).lower()
        hwid = str(getattr(porta_encontrada, "hwid", "")).lower()

        if "bluetooth" in descricao or "bthenum" in hwid:
            return None

        timeout_original = getattr(modbus, "timeout", 1.0)

        try:
            modbus.timeout = min(float(timeout_original), 0.25)

            if not modbus.conectado and not modbus.conectar():
                return None

            return modbus.ler_ipro()

        except Exception:
            try:
                modbus.desconectar()
            except Exception:
                pass
            return None

        finally:
            modbus.timeout = timeout_original

    def _processar_modbus_background(self, intervalo: float) -> bool:
        """Conecta e lê o iPro em segundo plano, sem bloquear a interface."""
        agora = time.monotonic()

        if self.future_auto is not None:
            if not self.future_auto.done():
                return False

            future = self.future_auto
            self.future_auto = None

            try:
                dados = future.result()
            except Exception:
                dados = None

            if dados:
                self._aplicar_leituras_ipro(dados)
                return True
            self.comunicacao_ipro = COMUNICACAO_DESCONECTADO

        if agora - self.ultimo_teste_auto >= intervalo:
            self.ultimo_teste_auto = agora
            self.future_auto = self.executor_modbus.submit(
                self._tarefa_auto_modbus
            )

        return False

    def _processar_auto_modbus(self) -> bool:
        """Compatibilidade: AUTO verifica o iPro a cada 5 segundos."""
        return self._processar_modbus_background(
            self.intervalo_teste_auto
        )

    def _atualizar(self) -> None:
        leitura_real_aplicada = False
        modo = self.modo_fonte

        if modo == "REAL":
            # REAL também lê em segundo plano. Assim, se o iPro parar
            # de responder quando entra em RUN, a janela não congela.
            leitura_real_aplicada = self._processar_modbus_background(
                intervalo=1.0
            )

        elif modo == "AUTO":
            leitura_real_aplicada = self._processar_modbus_background(
                intervalo=self.intervalo_teste_auto
            )

        if modo == "SIMULADO":
            self.ultimo_dados_ipro.clear()
            self.comunicacao_ipro = COMUNICACAO_OK
            self.possui_dados_reais = False
            self.gerador.atualizar(
                INTERVALO_ATUALIZACAO_MS / 1000.0
            )

        elif (
            modo == "AUTO"
            and not leitura_real_aplicada
            and not self.possui_dados_reais
        ):
            # Continua simulando enquanto procura o iPro.
            self.gerador.atualizar(
                INTERVALO_ATUALIZACAO_MS / 1000.0
            )

        elif modo == "REAL" and not leitura_real_aplicada:
            # Mantém a última leitura, mas a interface continua responsiva.
            pass

        modo_real = deve_usar_dados_reais(modo, self.possui_dados_reais)
        compressor = self.ultimo_dados_ipro.get("compressor")
        degelo = self.ultimo_dados_ipro.get("degelo")
        self.estado_maquina = calcular_estado_maquina(
            self.gerador,
            modo_real=modo_real,
            comunicacao=self.comunicacao_ipro,
            compressor=compressor if isinstance(compressor, bool) else None,
            degelo=degelo if isinstance(degelo, bool) else None,
        )
        self.sinotico.atualizar(self.gerador, self.estado_maquina)

        self._atualizar_tabela()
        self._atualizar_status()
        self._atualizar_alarmes()
        self._atualizar_informacoes()
        self._atualizar_rodape()

        self.contador_historico += 1

        if self.contador_historico >= 5:
            self.historico.salvar(self.gerador)
            self.contador_historico = 0

    def _atualizar_tabela(self) -> None:
        for linha, canal in enumerate(self.gerador.canais):
            unidade = canal.unidade or "-"

            if canal.habilitado:
                valor_eletrico, registrador = calcular_saida_canal(canal)
                tipo = canal.tipo_saida.upper().replace(" ", "")

                sinal = (
                    f"{valor_eletrico:.2f} V"
                    if tipo == "0-10V"
                    else f"{valor_eletrico:.2f} mA"
                )
                estado = "ATIVO"
            else:
                sinal = "-"
                registrador = 0
                estado = "RESERVA"

            valor_exibido = canal.valor if canal.habilitado else 0.0

            valores = [
                f"CH{canal.numero}",
                canal.nome,
                f"{valor_exibido:.2f} {unidade}",
                sinal,
                str(registrador),
                str(canal.endereco_modbus),
                estado,
            ]

            for coluna, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignCenter)

                if coluna == 6 and estado == "ATIVO":
                    item.setForeground(QColor("#16853a"))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))

                self.tabela.setItem(linha, coluna, item)

    def _atualizar_status(self) -> None:
        if self.gerador.pausado:
            self.status_execucao.atualizar("PAUSADA", "#bf7600")
        else:
            self.status_execucao.atualizar("ATIVA", "#14913c")

    def _atualizar_alarmes(self) -> None:
        estado_maquina = self.estado_maquina
        estados = [
            estado_maquina.alta_temperatura,
            estado_maquina.alta_pressao,
            estado_maquina.alta_temperatura_descarga,
            estado_maquina.baixa_pressao,
            estado_maquina.falha_sensor,
            estado_maquina.comunicacao != COMUNICACAO_OK,
        ]

        algum_alarme = estado_maquina.em_alarme

        for indice, (label, ativo) in enumerate(zip(self.labels_alarmes, estados)):
            cor_ativa = (
                "#c17800"
                if indice == 5 and estado_maquina.comunicacao == COMUNICACAO_PARCIAL
                else "#c62828"
            )
            label.setStyleSheet(
                f"""
                QLabel {{
                    color: {cor_ativa if ativo else '#6e7784'};
                    font-size:12px;
                    font-weight:{'900' if ativo else '400'};
                    padding:5px;
                }}
                """
            )

        if algum_alarme:
            self.label_resumo_alarme.setText(estado_maquina.falha_atual)
            self.label_resumo_alarme.setStyleSheet(
                """
                QLabel {
                    background:#fff2f2;
                    border:1px solid #e19a9a;
                    border-radius:6px;
                    color:#c62828;
                    font-size:14px;
                    font-weight:900;
                    padding:14px;
                }
                """
            )
        else:
            self.label_resumo_alarme.setText("SEM ALARMES")
            self.label_resumo_alarme.setStyleSheet(
                """
                QLabel {
                    background:#ffffff;
                    border:1px solid #cbd5e1;
                    border-radius:6px;
                    color:#16853a;
                    font-size:16px;
                    font-weight:900;
                    padding:14px;
                }
                """
            )

    def _dados_ipro_para_tela(self) -> dict[str, object]:
        """Retorna dados reais do iPro ou dados coerentes do simulador."""
        fonte_real_persistente = deve_usar_dados_reais(
            self.modo_fonte, self.possui_dados_reais
        )
        if fonte_real_persistente and self.ultimo_dados_ipro:
            return self.ultimo_dados_ipro

        modo = self.gerador.modo
        parado = modo == 1
        resfriando = modo == 2
        degelo = modo == 3

        if parado:
            temperatura_externa_simulada = 25.0
        elif resfriando:
            temperatura_externa_simulada = 28.0
        elif degelo:
            temperatura_externa_simulada = 32.0
        else:
            temperatura_externa_simulada = 25.0

        temperatura_evaporacao = None
        temperatura_condensacao = None
        superaquecimento = None
        subresfriamento = None
        abertura_valvula = 0.0
        capacidade_compressor = 0.0
        capacidade_condensador = 0.0

        unidade = False
        compressor = False
        evaporador = False
        condensador_1 = False
        condensador_2 = False
        solenoide_liquido = False

        if resfriando:
            temperatura_evaporacao = (
                self.gerador.temperatura_saturacao_succao or 0.0
            )
            temperatura_condensacao = (
                self.gerador.temperatura_saturacao_condensacao or 0.0
            )

            superaquecimento = max(
                0.0,
                float(self.gerador.superaquecimento or 0.0),
            )
            subresfriamento = max(
                0.0,
                float(self.gerador.subresfriamento or 0.0),
            )

            abertura_valvula = 50.0 - (
                superaquecimento - 8.0
            ) * 4.0
            abertura_valvula = max(
                10.0,
                min(90.0, abertura_valvula),
            )

            capacidade_compressor = max(
                0.0,
                min(
                    100.0,
                    float(
                        self.gerador.capacidade_compressor_percentual
                    ),
                ),
            )

            capacidade_condensador = max(
                30.0,
                min(
                    100.0,
                    30.0
                    + (
                        self.gerador.descarga.valor - 200.0
                    ) * 0.5,
                ),
            )

            unidade = True
            compressor = True
            evaporador = True
            condensador_1 = True
            condensador_2 = self.gerador.descarga.valor >= 270.0
            solenoide_liquido = compressor

        elif degelo:
            # Degelo por gás quente:
            # no modo simulado, a temperatura de evaporação acompanha
            # o aquecimento físico do evaporador.
            temperatura_evaporacao = self.gerador.evaporador.valor
            temperatura_condensacao = (
                self.gerador.temperatura_saturacao_condensacao or 0.0
            )

            superaquecimento = 0.0
            subresfriamento = 0.0
            abertura_valvula = 0.0

            capacidade_compressor = max(
                0.0,
                min(
                    100.0,
                    float(
                        self.gerador.capacidade_compressor_percentual
                    ),
                ),
            )
            capacidade_condensador = 0.0

            unidade = True
            compressor = True
            evaporador = False
            condensador_1 = False
            condensador_2 = False
            solenoide_liquido = False

        return {
            "temperatura_camara": self.gerador.camara.valor,
            "temperatura_evaporador": self.gerador.evaporador.valor,
            "temperatura_externa": temperatura_externa_simulada,
            "temperatura_insuflamento": (
                self.gerador.evaporador.valor + 3.0
            ),
            "temperatura_descarga": (
                self.gerador.temperatura_descarga.valor
            ),
            "temperatura_succao": (
                self.gerador.temperatura_succao.valor
            ),
            "temperatura_liquido": (
                self.gerador.temperatura_liquido.valor
            ),
            "temperatura_condensacao": temperatura_condensacao,
            "temperatura_evaporacao": temperatura_evaporacao,
            "pressao_succao_psi": self.gerador.succao.valor,
            "pressao_descarga_psi": self.gerador.descarga.valor,
            "superaquecimento": superaquecimento,
            "subresfriamento": subresfriamento,
            "abertura_valvula": abertura_valvula,
            "capacidade_compressor": capacidade_compressor,
            "capacidade_condensador": capacidade_condensador,
            "unidade": unidade,
            "compressor": compressor,
            "evaporador": evaporador,
            "condensador_1": condensador_1,
            "condensador_2": condensador_2,
            "degelo": degelo,
            "solenoide_liquido": solenoide_liquido,
        }

    def _atualizar_painel_ipro(self) -> None:
        if not hasattr(self, "labels_ipro"):
            return

        dados = self._dados_ipro_para_tela()
        leituras = dados.get("_leituras", {})
        usando_dados_reais = bool(leituras) and (
            self.modo_fonte == "REAL"
            or (self.modo_fonte == "AUTO" and self.possui_dados_reais)
        )
        unidades = {
            "temperatura_camara": "°C",
            "temperatura_evaporador": "°C",
            "temperatura_externa": "°C",
            "temperatura_insuflamento": "°C",
            "temperatura_descarga": "°C",
            "temperatura_succao": "°C",
            "temperatura_liquido": "°C",
            "temperatura_condensacao": "°C",
            "temperatura_evaporacao": "°C",
            "pressao_succao_psi": "PSI",
            "pressao_descarga_psi": "PSI",
            "superaquecimento": "°C",
            "subresfriamento": "°C",
            "abertura_valvula": "%",
            "capacidade_compressor": "%",
            "capacidade_condensador": "%",
        }

        for chave, label in self.labels_ipro.items():
            chave_real = {
                "pressao_succao_psi": "pressao_succao_bar",
                "pressao_descarga_psi": "pressao_descarga_bar",
            }.get(chave, chave)
            leitura = leituras.get(chave_real, {}) if usando_dados_reais else {}
            valor = leitura.get("valor") if leitura else dados.get(chave, None)
            unidade = (
                str(leitura.get("unidade_interface", unidades[chave]))
                if leitura
                else unidades[chave]
            )
            qualidade = str(leitura.get("qualidade", "")) if leitura else ""
            if usando_dados_reais and self.comunicacao_ipro == COMUNICACAO_DESCONECTADO:
                qualidade = QUALIDADE_DESATUALIZADA if valor is not None else "SEM_DADOS"

            if valor is None and chave in (
                "temperatura_evaporacao",
                "temperatura_condensacao",
                "superaquecimento",
                "subresfriamento",
            ):
                sufixo = f" [{qualidade}]" if qualidade else ""
                label.setText(f"-- {unidade}{sufixo}")
            else:
                try:
                    sufixo = f" [{qualidade}]" if qualidade else ""
                    label.setText(f"{float(valor):.2f} {unidade}{sufixo}")
                except (TypeError, ValueError):
                    sufixo = f" [{qualidade}]" if qualidade else ""
                    label.setText(f"-- {unidade}{sufixo}")

        for chave, label in self.labels_ipro_status.items():
            leitura = leituras.get(chave, {}) if usando_dados_reais else {}
            valor = leitura.get("valor") if leitura else dados.get(chave)
            qualidade = str(leitura.get("qualidade", "")) if leitura else ""
            if usando_dados_reais and self.comunicacao_ipro == COMUNICACAO_DESCONECTADO:
                qualidade = QUALIDADE_DESATUALIZADA if valor is not None else "SEM_DADOS"
            if valor is None:
                label.setText("SEM COMUNICAÇÃO")
                label.setStyleSheet("font-weight:900; color:#c17800;")
            else:
                ativo = valor is True
                texto = "ON" if ativo else "OFF"
                label.setText(f"{texto} [{qualidade}]" if qualidade else texto)
                label.setStyleSheet(
                    "font-weight:900; color:#c17800;"
                    if qualidade in {QUALIDADE_DESATUALIZADA, "SEM_DADOS"}
                    else "font-weight:900; color:#16853a;"
                    if ativo
                    else "font-weight:900; color:#6e7784;"
                )

    def _atualizar_informacoes(self) -> None:
        falha = self.estado_maquina.falha_atual
        execucao = "PAUSADA" if self.gerador.pausado else "ATIVA"

        self.info_modo.setText(
            f"Modo atual: <b style='color:#123b75'>{self.estado_maquina.nome_modo}</b>"
        )
        self.info_agressividade.setText(
            f"Agressividade: <b style='color:#123b75'>{self.gerador.agressividade}%</b>"
        )
        self.info_execucao.setText(
            f"Execução: <b style='color:#16853a'>{execucao}</b>"
        )
        self.info_falha.setText(
            f"Falha atual: <b style='color:#123b75'>{falha}</b>"
        )

        superaquecimento = self.gerador.superaquecimento
        subresfriamento = self.gerador.subresfriamento
        saturacao_succao = self.gerador.temperatura_saturacao_succao
        saturacao_condensacao = (
            self.gerador.temperatura_saturacao_condensacao
        )

        if superaquecimento is None:
            texto_superaquecimento = "-- °C"
        else:
            texto_superaquecimento = (
                f"{superaquecimento:.2f} °C"
                f"<br><span style='font-size:10px;'>"
                f"Tsat: {saturacao_succao:.2f} °C</span>"
            )

        if subresfriamento is None:
            texto_subresfriamento = "-- °C"
        else:
            texto_subresfriamento = (
                f"{subresfriamento:.2f} °C"
                f"<br><span style='font-size:10px;'>"
                f"Tsat: {saturacao_condensacao:.2f} °C</span>"
            )

        self.info_superaquecimento.setText(
            "Superaquecimento: "
            f"<b style='color:#8a42bd'>{texto_superaquecimento}</b>"
        )
        self.info_subresfriamento.setText(
            "Sub-resfriamento: "
            f"<b style='color:#126cc1'>{texto_subresfriamento}</b>"
        )

        self._atualizar_painel_ipro()

    def _atualizar_rodape(self) -> None:
        config = carregar()

        modo = self.modo_fonte
        porta = str(config.get("porta", "COM3"))
        baudrate = int(config.get("baudrate", 9600))
        slave_id = int(config.get("slave", 1))
        conectado = False
        ultimo_erro = ""

        if self.janela_modbus is not None:
            modbus = self.janela_modbus.modbus
            conectado = bool(
                modbus.conectado
                and not modbus.simulado
            )
            porta = modbus.porta
            baudrate = modbus.baudrate
            slave_id = modbus.slave_id
            ultimo_erro = modbus.ultimo_erro

        if modo == "SIMULADO":
            self.status_modbus.atualizar(
                "SIMULADO",
                "#c17800",
            )
            texto_estado = "DESCONECTADO — SIMULADO"

        elif self.possui_dados_reais and self.comunicacao_ipro == COMUNICACAO_OK:
            agora = datetime.now().strftime("%H:%M:%S")
            self.rodape_ultimo.setText(f"ÚLTIMA LEITURA:\n{agora}")
            self.status_modbus.atualizar(
                "CONECTADO — REAL",
                "#16853a",
            )
            texto_estado = "CONECTADO — REAL"

        elif self.possui_dados_reais and self.comunicacao_ipro == COMUNICACAO_PARCIAL:
            self.status_modbus.atualizar(
                "COMUNICAÇÃO PARCIAL",
                "#c17800",
            )
            texto_estado = "DADOS REAIS — PARCIAL"

        elif self.possui_dados_reais:
            self.status_modbus.atualizar(
                "SEM COMUNICAÇÃO",
                "#c62828",
            )
            texto_estado = "DADOS REAIS — DESATUALIZADOS"

        elif modo == "AUTO":
            self.status_modbus.atualizar(
                "AUTO — SIMULANDO",
                "#c17800",
            )
            texto_estado = "AUTO — AGUARDANDO iPRO"

        else:
            self.status_modbus.atualizar(
                "REAL — SEM COMUNICAÇÃO",
                "#c62828",
            )
            texto_estado = "DESCONECTADO — REAL"

        self.rodape_modbus.setText(
            f"RS485/Modbus\n{texto_estado}"
        )
        self.rodape_com.setText(f"COM:\n{porta}")
        self.rodape_baud.setText(f"BAUD:\n{baudrate}")
        self.rodape_slave.setText(f"SLAVE ID:\n{slave_id}")
        self.rodape_pacotes.setText(
            f"PACOTES/LIGAÇÕES:\n{self.pacotes_enviados}"
        )

        if ultimo_erro and modo != "SIMULADO":
            self.rodape_ultimo.setToolTip(ultimo_erro)
        else:
            self.rodape_ultimo.setToolTip("")


    def closeEvent(self, event) -> None:
        """Encerra a tarefa Modbus sem deixar o programa preso ao fechar."""
        try:
            if self.painel_simulador_ipro is not None:
                self.painel_simulador_ipro.servidor.parar()
        except Exception:
            pass

        try:
            if self.janela_modbus is not None:
                self.janela_modbus.modbus.desconectar()
        except Exception:
            pass

        try:
            self.executor_modbus.shutdown(
                wait=False,
                cancel_futures=True,
            )
        except Exception:
            pass

        event.accept()



def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    janela = JanelaFinal()
    janela.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
