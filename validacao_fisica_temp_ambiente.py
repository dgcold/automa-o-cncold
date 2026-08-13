from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from simulador_ipro_rs485 import crc16_modbus
from validacao_temp_ambiente_core import (
    BAUDRATE, BYTESIZE, ENDERECO, ESCALA, ESPERA_ATUALIZACAO_S, FUNCAO,
    LeitorIPRO, PASSOS_C, PARIDADE, PORTA, QUANTIDADE, RESULTADOS,
    SLAVE, STOPBITS, comparar_estados_ipro, resposta_controlada,
)


class ServidorValidacao:
    def __init__(
        self,
        log: Callable[[str], None],
        ao_responder: Callable[[dict], None],
    ) -> None:
        self.log = log
        self.ao_responder = ao_responder
        self._bruto = 0
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial = None

    @property
    def ativo(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def definir_temperatura(self, temperatura_c: float) -> int:
        if temperatura_c not in PASSOS_C:
            raise ValueError("valor fora dos cinco passos autorizados")
        bruto = round(temperatura_c * ESCALA)
        with self._lock:
            self._bruto = bruto
        return bruto

    def iniciar(self) -> None:
        if self.ativo:
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._executar, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _executar(self) -> None:
        try:
            import serial

            self._serial = serial.Serial(
                PORTA, BAUDRATE, bytesize=BYTESIZE, parity=PARIDADE,
                stopbits=STOPBITS, timeout=0.05,
            )
            self.log("SERVIDOR ATIVO — COM8 / 9600 / 8N2 — filtro exclusivo 1/04/10/6")
            buffer = bytearray()
            while not self._parar.is_set():
                dados = self._serial.read(256)
                if dados:
                    buffer.extend(dados)
                while len(buffer) >= 8:
                    frame = bytes(buffer[:8])
                    if crc16_modbus(frame[:6]) != int.from_bytes(frame[6:8], "little"):
                        del buffer[0]
                        continue
                    del buffer[:8]
                    with self._lock:
                        bruto = self._bruto
                    resultado = resposta_controlada(frame, bruto)
                    if resultado is None:
                        self.log(
                            "IGNORADO — somente ID=1 FC=04 END=10 QTD=6 é autorizado"
                        )
                        continue
                    resposta, valores = resultado
                    time.sleep(0.005)
                    self._serial.write(resposta)
                    self._serial.flush()
                    agora = time.time()
                    exibicao = [bruto, 0, 0, 0, 0, 0]
                    self.log(f"RESPONDIDO ID=1 FC=04 END=10 QTD=6 VAL={exibicao}")
                    self.ao_responder({
                        "timestamp_unix": agora,
                        "timestamp": datetime.fromtimestamp(agora).astimezone().isoformat(),
                        "slave": SLAVE,
                        "funcao": FUNCAO,
                        "endereco": ENDERECO,
                        "quantidade": QUANTIDADE,
                        "offset": 0,
                        "bruto_assinado": bruto,
                        "bruto_wire": valores[0],
                        "valor_escalado_c": bruto / ESCALA,
                        "valores_resposta": exibicao,
                    })
        except Exception as erro:
            if not self._parar.is_set():
                self.log(f"ERRO: {erro}")
        finally:
            self._serial = None


class Evidencia:
    def __init__(self) -> None:
        inicio = datetime.now().astimezone()
        pasta = Path(__file__).with_name("evidencias_validacao_modbus")
        pasta.mkdir(exist_ok=True)
        self.arquivo = pasta / f"temp_ambiente_s1_fc04_r10_{inicio:%Y%m%d_%H%M%S}.jsonl"
        self.registrar("sessao_iniciada", {
            "inicio": inicio.isoformat(),
            "alvo": {"slave": 1, "funcao": 4, "endereco": 10, "quantidade": 6},
            "serial": {"porta": "COM8", "baudrate": 9600, "formato": "8N2"},
            "sinal_candidato": "Temperatura Ambiente / sns[1] / W1[0]",
            "regra": "resultado exclusivamente manual; sem promoção automática da matriz",
        })

    def registrar(self, evento: str, dados: dict) -> None:
        linha = {
            "evento": evento,
            "registrado_em": datetime.now().astimezone().isoformat(),
            **dados,
        }
        with self.arquivo.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


class JanelaValidacao(QWidget):
    mensagem = Signal(str)
    resposta = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Validação física controlada — Temperatura Ambiente")
        self.resize(1040, 760)
        self.evidencia = Evidencia()
        self.servidor = ServidorValidacao(self.mensagem.emit, self.resposta.emit)
        self.leitor = LeitorIPRO()
        self.indice_passo = 0
        self.passo_aplicado = False
        self.tempo_restante = 0
        self.ultima_resposta: dict | None = None
        self.estado_ipro_antes: dict | None = None
        self.estado_ipro_depois: dict | None = None
        self.ultima_correlacao: dict | None = None
        self.resultados: list[dict] = []
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._contar_tempo)
        self._montar()
        self.mensagem.connect(self.log.appendPlainText)
        self.resposta.connect(self._registrar_resposta)
        self._mostrar_passo()

    def _montar(self) -> None:
        layout = QVBoxLayout(self)
        aviso = QLabel(
            "TESTE EXCLUSIVO: Slave 1 / FC04 / END 10 / QTD 6. "
            "Somente offset 0 varia; offsets 1–5 permanecem em zero. "
            "Esta tela nunca confirma o mapa automaticamente."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("font-weight:700; color:#8a5200; padding:10px;")
        layout.addWidget(aviso)

        barra = QHBoxLayout()
        self.botao_iniciar = QPushButton("Iniciar COM8")
        self.botao_parar = QPushButton("Parar COM8")
        self.botao_iniciar.clicked.connect(self.servidor.iniciar)
        self.botao_parar.clicked.connect(self.servidor.parar)
        barra.addWidget(self.botao_iniciar)
        barra.addWidget(self.botao_parar)
        self.check_correlacao_ipro = QCheckBox("Ler iPro real antes/depois")
        self.check_correlacao_ipro.setChecked(True)
        barra.addWidget(self.check_correlacao_ipro)
        barra.addStretch()
        self.rotulo_arquivo = QLabel(f"Evidência: {self.evidencia.arquivo.name}")
        barra.addWidget(self.rotulo_arquivo)
        self.rotulo_status_correlacao = QLabel("Correlação iPro: pronta")
        barra.addWidget(self.rotulo_status_correlacao)
        layout.addLayout(barra)

        grupo = QGroupBox("Passo controlado")
        grade = QGridLayout(grupo)
        titulos = (
            "VALOR ENVIADO PELO SIMULADOR", "VALOR BRUTO", "VALOR ESCALADO",
            "REGISTRADOR", "OFFSET", "TEMPO",
        )
        self.valores = []
        for coluna, titulo in enumerate(titulos):
            rotulo = QLabel(titulo)
            rotulo.setStyleSheet("font-weight:700;")
            valor = QLabel("—")
            valor.setStyleSheet("font-size:20px; padding:8px;")
            grade.addWidget(rotulo, 0, coluna)
            grade.addWidget(valor, 1, coluna)
            self.valores.append(valor)
        layout.addWidget(grupo)

        passos = QHBoxLayout()
        self.grupo_passos = QButtonGroup(self)
        for indice, temperatura in enumerate(PASSOS_C):
            botao = QRadioButton(f"{temperatura:+.1f} °C")
            botao.setEnabled(False)
            self.grupo_passos.addButton(botao, indice)
            passos.addWidget(botao)
        layout.addLayout(passos)

        acoes = QHBoxLayout()
        self.botao_aplicar = QPushButton("Aplicar passo atual")
        self.botao_aplicar.clicked.connect(self._aplicar_passo)
        acoes.addWidget(self.botao_aplicar)
        self.botoes_resultado = []
        for resultado in RESULTADOS:
            botao = QPushButton(resultado)
            botao.setEnabled(False)
            botao.clicked.connect(lambda _, r=resultado: self._registrar_resultado(r))
            acoes.addWidget(botao)
            self.botoes_resultado.append(botao)
        layout.addLayout(acoes)

        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels([
            "Passo", "Enviado", "Bruto", "Escalado", "Última resposta",
            "Resultado manual", "Correlação iPro", "Observação W1[0]",
        ])
        layout.addWidget(self.tabela, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(170)
        layout.addWidget(self.log)

    def _mostrar_passo(self) -> None:
        if self.indice_passo >= len(PASSOS_C):
            self.botao_aplicar.setEnabled(False)
            self.valores[5].setText("CONCLUÍDO")
            self.mensagem.emit(
                "SEQUÊNCIA CONCLUÍDA — revise o arquivo de evidência; a matriz não foi alterada."
            )
            self.evidencia.registrar("sessao_concluida", {"resultados": self.resultados})
            return
        temperatura = PASSOS_C[self.indice_passo]
        bruto = round(temperatura * ESCALA)
        self.grupo_passos.button(self.indice_passo).setChecked(True)
        self.valores[0].setText(f"{temperatura:+.1f} °C")
        self.valores[1].setText(str(bruto))
        self.valores[2].setText(f"{bruto / ESCALA:+.1f} °C")
        self.valores[3].setText("10")
        self.valores[4].setText("0")
        self.valores[5].setText("aguardando aplicação")
        self.botao_aplicar.setEnabled(True)
        self.passo_aplicado = False

    def _aplicar_passo(self) -> None:
        if not self.servidor.ativo:
            QMessageBox.warning(self, "COM8 inativa", "Inicie a COM8 antes de aplicar o passo.")
            return
        temperatura = PASSOS_C[self.indice_passo]
        bruto = self.servidor.definir_temperatura(temperatura)
        self.passo_aplicado = True
        self.ultima_resposta = None
        if self.check_correlacao_ipro.isChecked():
            self._ler_estado_ipro("antes")
        self.tempo_restante = ESPERA_ATUALIZACAO_S
        self.botao_aplicar.setEnabled(False)
        for botao in self.botoes_resultado:
            botao.setEnabled(False)
        self.valores[5].setText(f"{self.tempo_restante} s")
        self.timer.start()
        self.evidencia.registrar("passo_aplicado", {
            "passo": self.indice_passo + 1,
            "valor_enviado_c": temperatura,
            "valor_bruto": bruto,
            "valor_escalado_c": bruto / ESCALA,
            "registrador": 10,
            "offset": 0,
            "outros_offsets": [0, 0, 0, 0, 0],
            "espera_s": ESPERA_ATUALIZACAO_S,
        })
        self.mensagem.emit(
            f"PASSO {self.indice_passo + 1}/5 aplicado: {temperatura:+.1f} °C; "
            f"aguardando {ESPERA_ATUALIZACAO_S} s para avaliação manual de W1[0]."
        )

    def _contar_tempo(self) -> None:
        self.tempo_restante -= 1
        if self.tempo_restante > 0:
            self.valores[5].setText(f"{self.tempo_restante} s")
            return
        self.timer.stop()
        self.valores[5].setText("pronto para avaliar")
        if self.check_correlacao_ipro.isChecked():
            self._ler_estado_ipro("depois")
        for botao in self.botoes_resultado:
            botao.setEnabled(True)
        self.evidencia.registrar("espera_concluida", {
            "passo": self.indice_passo + 1,
            "houve_resposta_exata": self.ultima_resposta is not None,
        })

    def _registrar_resposta(self, dados: dict) -> None:
        self.ultima_resposta = dados
        self.evidencia.registrar("resposta_enviada", dados)

    def _registrar_resultado(self, resultado: str) -> None:
        if not self.passo_aplicado or self.timer.isActive():
            return
        temperatura = PASSOS_C[self.indice_passo]
        dados = {
            "passo": self.indice_passo + 1,
            "valor_enviado_c": temperatura,
            "valor_bruto": round(temperatura * ESCALA),
            "resultado_manual": resultado,
            "w1_observado": resultado != "NÃO VALIDADO",
            "ultima_resposta": self.ultima_resposta,
        }
        self.resultados.append(dados)
        self.evidencia.registrar("avaliacao_manual", dados)
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)

        candidatos = []
        if self.ultima_correlacao and self.ultima_correlacao.get("passo") == self.indice_passo + 1:
            candidatos = [item["nome"] for item in self.ultima_correlacao.get("candidatos", [])]

        valores = (
            str(self.indice_passo + 1), f"{temperatura:+.1f} °C",
            str(round(temperatura * ESCALA)), f"{temperatura:+.1f} °C",
            self.ultima_resposta["timestamp"] if self.ultima_resposta else "nenhuma",
            resultado,
            ", ".join(candidatos) if candidatos else "sem leitura iPro",
            "registrada pelo operador" if resultado != "NÃO VALIDADO" else "não observável",
        )
        for coluna, valor in enumerate(valores):
            self.tabela.setItem(linha, coluna, QTableWidgetItem(valor))
        self.tabela.resizeColumnsToContents()
        self.indice_passo += 1
        self._mostrar_passo()

    def _ler_estado_ipro(self, etapa: str) -> None:
        self.rotulo_status_correlacao.setText(f"Correlação iPro: lendo {etapa}")
        try:
            estado = self.leitor.ler()
        except Exception as erro:
            mensagem_tecnica = str(erro)
            self.mensagem.emit(f"Falha lendo iPro {etapa}: {mensagem_tecnica}")
            self.rotulo_status_correlacao.setText(
                f"Correlação iPro: erro — {mensagem_tecnica}"
            )
            return

        if etapa == "antes":
            self.estado_ipro_antes = estado
        else:
            self.estado_ipro_depois = estado

        self.evidencia.registrar(f"estado_ipro_{etapa}", {
            "passo": self.indice_passo + 1,
            "estado": {
                chave: valor
                for chave, valor in estado.items()
                if not chave.startswith("_")
            },
        })
        self.mensagem.emit(f"Estado iPro {etapa} capturado com sucesso.")
        self.rotulo_status_correlacao.setText(
            f"Correlação iPro: estado {etapa} lido"
        )

        if etapa == "depois" and self.estado_ipro_antes is not None:
            self._comparar_estados_ipro()

    def _comparar_estados_ipro(self) -> None:
        antes = self.estado_ipro_antes or {}
        depois = self.estado_ipro_depois or {}
        linhas = comparar_estados_ipro(antes, depois)
        candidatos = [
            {"nome": linha["nome"], "delta": linha["delta"],
             "antes": linha["antes"], "depois": linha["depois"]}
            for linha in linhas
            if linha["mudou"]
        ]
        self.ultima_correlacao = {
            "passo": self.indice_passo + 1,
            "candidatos": candidatos,
        }
        self.evidencia.registrar("correlacao_possivel", {
            "passo": self.indice_passo + 1,
            "mudancas": len(candidatos),
            "candidatos": candidatos,
        })
        self.mensagem.emit(
            f"Correlação iPro: {len(candidatos)} possíveis variáveis mudaram."
        )
        self.rotulo_status_correlacao.setText(
            f"Correlação iPro: {len(candidatos)} mudanças detectadas"
        )

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.servidor.parar()
        self.leitor.desconectar()
        self.evidencia.registrar("sessao_encerrada", {
            "passos_concluidos": len(self.resultados),
            "matriz_alterada": False,
        })
        event.accept()


def main() -> None:
    app = QApplication([])
    janela = JanelaValidacao()
    janela.show()
    app.exec()


if __name__ == "__main__":
    main()
