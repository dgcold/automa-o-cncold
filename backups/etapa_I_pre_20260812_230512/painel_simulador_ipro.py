from __future__ import annotations

import re
import csv
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from simulador_ipro_rs485 import EstadoSimulador, ServidorRTU, comparar_capturas


class PainelSimuladorIPro(QWidget):
    mensagem_recebida = Signal(str)
    consulta_recebida = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Simulador de equipamentos - iPro MASTER")
        self.resize(980, 780)
        self.estado = EstadoSimulador()
        self.capturas = {"A": {}, "B": {}}
        self.linhas_comparacao = []
        self.estado_captura = None
        self.servidor = ServidorRTU(
            self.estado,
            self.mensagem_recebida.emit,
            self.consulta_recebida.emit,
        )
        self._montar()
        self.mensagem_recebida.connect(self.log.appendPlainText)
        self.consulta_recebida.connect(self._registrar_consulta)

    def _montar(self) -> None:
        layout = QVBoxLayout(self)
        aviso = QLabel(
            "COM8 / 9600 / 8N2 — Slave 1 FC04 — Slave 2 FC03\n"
            "Os significados dos registradores ainda são DESCONHECIDOS. "
            "Associe um sinal somente após confirmar a correlação no iPro."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("font-weight:700; color:#9a5b00; padding:8px;")
        layout.addWidget(aviso)

        botoes = QHBoxLayout()
        iniciar = QPushButton("Iniciar servidor")
        parar = QPushButton("Parar")
        iniciar.clicked.connect(self.servidor.iniciar)
        parar.clicked.connect(self.servidor.parar)
        botoes.addWidget(iniciar)
        botoes.addWidget(parar)
        botoes.addStretch()
        layout.addLayout(botoes)

        form = QFormLayout()
        destinos = ["Não associado"]
        for slave, bloco in self.estado.config["blocos_confirmados"].items():
            destinos.extend(f"Slave {slave} / reg {e}" for e in bloco["enderecos_iniciais"])

        for nome, sinal in self.estado.config["sinais"].items():
            linha = QWidget()
            h = QHBoxLayout(linha)
            h.setContentsMargins(0, 0, 0, 0)
            valor = QDoubleSpinBox()
            valor.setRange(float(sinal["minimo"]), float(sinal["maximo"]))
            valor.setDecimals(2)
            valor.setSuffix(f" {sinal['unidade']}")
            valor.setValue(float(sinal["valor"]))
            destino = QComboBox()
            destino.addItems(destinos)
            destino.setEditable(True)
            escala = QDoubleSpinBox()
            escala.setRange(0.001, 10000.0)
            escala.setValue(10.0)
            escala.setPrefix("x ")
            associacao = sinal.get("associacao")
            if associacao:
                texto = f"Slave {associacao['slave']} / reg {associacao['endereco']}"
                destino.setCurrentText(texto)
                escala.setValue(float(associacao["escala"]))

            def mudar_valor(v, n=nome):
                aplicado = self.estado.definir_sinal(n, v)
                if not aplicado:
                    self.mensagem_recebida.emit(f"{n}: valor alterado, mas ainda sem associação")

            def associar(_=None, n=nome, d=destino, e=escala):
                if d.currentIndex() == 0:
                    self.estado.associar_sinal(n, None, None)
                    return
                correspondencia = re.fullmatch(
                    r"Slave\s+(\d+)\s*/\s*reg\s+(\d+)", d.currentText().strip()
                )
                if not correspondencia:
                    self.mensagem_recebida.emit(
                        f"Associação inválida para {n}; use 'Slave N / reg N'."
                    )
                    return
                slave, endereco = map(int, correspondencia.groups())
                self.estado.associar_sinal(n, slave, endereco, e.value())
                self.mensagem_recebida.emit(
                    f"{n} associado pelo usuário a {d.currentText()} com escala {e.value()}"
                )

            valor.valueChanged.connect(mudar_valor)
            destino.currentIndexChanged.connect(associar)
            escala.valueChanged.connect(associar)
            h.addWidget(valor, 2)
            h.addWidget(destino, 2)
            h.addWidget(escala, 1)
            form.addRow(sinal["nome"], linha)
        layout.addLayout(form)

        captura = QHBoxLayout()
        self.label_captura = QLabel("Captura: inativa")
        botao_a = QPushButton("Capturar Estado A")
        botao_b = QPushButton("Capturar Estado B")
        botao_comparar = QPushButton("Comparar A × B")
        botao_a.clicked.connect(lambda: self._iniciar_captura("A"))
        botao_b.clicked.connect(lambda: self._iniciar_captura("B"))
        botao_comparar.clicked.connect(self._comparar)
        captura.addWidget(botao_a)
        captura.addWidget(botao_b)
        captura.addWidget(botao_comparar)
        captura.addWidget(self.label_captura)
        captura.addStretch()
        layout.addLayout(captura)

        topo_comparacao = QHBoxLayout()
        self.resumo_comparacao = QLabel(
            "0 posições analisadas | 0 alterações encontradas."
        )
        self.resumo_comparacao.setStyleSheet("font-weight:700;")
        self.filtro_somente_alteracoes = QCheckBox(
            "Mostrar somente alterações"
        )
        self.filtro_somente_alteracoes.setChecked(True)
        self.filtro_somente_alteracoes.toggled.connect(
            self._atualizar_tabela_comparacao
        )
        topo_comparacao.addWidget(self.resumo_comparacao)
        topo_comparacao.addStretch()
        topo_comparacao.addWidget(self.filtro_somente_alteracoes)
        layout.addLayout(topo_comparacao)

        self.tabela_comparacao = QTableWidget(0, 9)
        self.tabela_comparacao.setHorizontalHeaderLabels([
            "Slave", "FC", "Bloco", "Posição", "Endereço",
            "Estado A", "Estado B", "Delta", "Mudou",
        ])
        self.tabela_comparacao.setMinimumHeight(190)
        layout.addWidget(self.tabela_comparacao, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("As consultas recebidas do iPro aparecerão aqui.")
        layout.addWidget(self.log, 1)

    def _iniciar_captura(self, nome: str) -> None:
        self.capturas[nome] = {}
        self.estado_captura = nome
        self.label_captura.setText(f"Capturando Estado {nome}…")
        self.mensagem_recebida.emit(
            f"CAPTURA {nome} INICIADA: aguardando ciclos de consulta do iPro."
        )

    def _registrar_consulta(self, consulta: dict) -> None:
        if self.estado_captura not in ("A", "B"):
            return
        chave = (
            int(consulta["slave"]),
            int(consulta["funcao"]),
            int(consulta["endereco"]),
        )
        # Congela a primeira resposta de cada bloco. Assim, ao mover o controle
        # para preparar o Estado B, o Estado A não é sobrescrito no intervalo.
        self.capturas[self.estado_captura].setdefault(
            chave, list(consulta["valores"])
        )
        total = len(self.capturas[self.estado_captura])
        self.label_captura.setText(
            f"Capturando Estado {self.estado_captura}: {total} blocos"
        )

    def _comparar(self) -> None:
        self.estado_captura = None
        linhas = comparar_capturas(self.capturas["A"], self.capturas["B"])
        self.linhas_comparacao = linhas
        mudancas = sum(1 for linha in linhas if linha["mudou"])
        termo = "alteração encontrada" if mudancas == 1 else "alterações encontradas"
        self.resumo_comparacao.setText(
            f"{len(linhas)} posições analisadas | {mudancas} {termo}."
        )
        self._atualizar_tabela_comparacao()
        arquivo = self._salvar_comparacao(linhas)
        self.label_captura.setText(
            f"Comparação: {mudancas} de {len(linhas)} posições mudaram"
        )
        self.mensagem_recebida.emit(
            f"COMPARAÇÃO CONCLUÍDA: {mudancas}/{len(linhas)} posições alteradas. "
            f"Arquivo: {arquivo}"
        )

    def _atualizar_tabela_comparacao(self) -> None:
        linhas = self.linhas_comparacao
        if self.filtro_somente_alteracoes.isChecked():
            linhas = [linha for linha in linhas if linha["mudou"]]
        self.tabela_comparacao.setRowCount(len(linhas))
        campos = (
            "slave", "funcao", "inicio_bloco", "posicao", "endereco",
            "estado_a", "estado_b", "delta", "mudou",
        )
        for linha_indice, linha in enumerate(linhas):
            for coluna, campo in enumerate(campos):
                valor = linha[campo]
                texto = "—" if valor is None else "SIM" if valor is True else "NÃO" if valor is False else str(valor)
                item = QTableWidgetItem(texto)
                if linha["mudou"]:
                    item.setBackground(QColor("#fff2a8"))
                self.tabela_comparacao.setItem(linha_indice, coluna, item)
        self.tabela_comparacao.resizeColumnsToContents()

    def _salvar_comparacao(self, linhas: list[dict]) -> Path:
        pasta = Path(__file__).with_name("capturas_rs485")
        pasta.mkdir(exist_ok=True)
        sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = pasta / f"comparacao_estados_{sufixo}.csv"
        json_path = pasta / f"capturas_estados_{sufixo}.json"
        campos = [
            "slave", "funcao", "inicio_bloco", "posicao", "endereco",
            "estado_a", "estado_b", "delta", "mudou",
        ]
        with csv_path.open("w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
            escritor.writeheader()
            escritor.writerows(linhas)
        serializavel = {
            nome: [
                {"slave": chave[0], "funcao": chave[1], "endereco": chave[2], "valores": valores}
                for chave, valores in sorted(captura.items())
            ]
            for nome, captura in self.capturas.items()
        }
        with json_path.open("w", encoding="utf-8") as arquivo:
            json.dump(serializavel, arquivo, indent=2, ensure_ascii=False)
        return csv_path

    def closeEvent(self, event) -> None:
        self.servidor.parar()
        event.accept()
