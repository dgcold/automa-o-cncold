import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config_modbus import carregar, mesclar_configuracao, salvar
from modbus_rs485 import ModbusRS485


class JanelaModbus(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Configuração Modbus RS485")
        self.setFixedSize(430, 390)

        self.modbus = ModbusRS485()

        self._montar_interface()
        self._carregar_configuracao()
        self._atualizar_status()

    def _montar_interface(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(20, 20, 20, 20)
        layout_principal.setSpacing(14)

        titulo = QLabel("CONFIGURAÇÃO MODBUS RS485")
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #173f73;"
        )
        layout_principal.addWidget(titulo)

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignRight)

        self.combo_porta = QComboBox()
        self.combo_porta.setEditable(True)
        self._carregar_portas()

        self.combo_baudrate = QComboBox()
        self.combo_baudrate.addItems(
            ["9600", "19200", "38400", "57600", "115200"]
        )

        self.combo_paridade = QComboBox()
        self.combo_paridade.addItem("Nenhuma", "N")
        self.combo_paridade.addItem("Par", "E")
        self.combo_paridade.addItem("Ímpar", "O")

        self.combo_stopbits = QComboBox()
        self.combo_stopbits.addItems(["1", "2"])

        self.spin_slave = QSpinBox()
        self.spin_slave.setRange(1, 247)

        self.combo_modo = QComboBox()
        self.combo_modo.addItems(["SIMULADO", "REAL"])

        formulario.addRow("Porta COM:", self.combo_porta)
        formulario.addRow("Baud rate:", self.combo_baudrate)
        formulario.addRow("Paridade:", self.combo_paridade)
        formulario.addRow("Stop bits:", self.combo_stopbits)
        formulario.addRow("Slave ID:", self.spin_slave)
        formulario.addRow("Modo:", self.combo_modo)

        layout_principal.addLayout(formulario)

        self.label_status = QLabel()
        self.label_status.setAlignment(Qt.AlignCenter)
        self.label_status.setMinimumHeight(42)
        layout_principal.addWidget(self.label_status)

        botoes = QHBoxLayout()

        self.botao_conectar = QPushButton("Conectar")
        self.botao_conectar.clicked.connect(self._conectar)

        self.botao_desconectar = QPushButton("Desconectar")
        self.botao_desconectar.clicked.connect(self._desconectar)

        self.botao_salvar = QPushButton("Salvar")
        self.botao_salvar.clicked.connect(self._salvar_configuracao)

        self.botao_fechar = QPushButton("Fechar")
        self.botao_fechar.clicked.connect(self.close)

        botoes.addWidget(self.botao_conectar)
        botoes.addWidget(self.botao_desconectar)
        botoes.addWidget(self.botao_salvar)
        botoes.addWidget(self.botao_fechar)

        layout_principal.addLayout(botoes)

        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
                font-size: 12px;
                background: #f4f7fb;
            }

            QComboBox, QSpinBox {
                background: white;
                border: 1px solid #bfc9d6;
                border-radius: 5px;
                padding: 6px;
                min-height: 28px;
            }

            QPushButton {
                background: white;
                border: 1px solid #bfc9d6;
                border-radius: 5px;
                padding: 8px 12px;
                font-weight: 700;
            }

            QPushButton:hover {
                background: #eaf3ff;
                border-color: #5b8fc7;
            }
            """
        )

    def _carregar_portas(self) -> None:
        self.combo_porta.clear()

        portas = []

        try:
            from serial.tools import list_ports

            portas = [
                porta.device
                for porta in list_ports.comports()
            ]
        except ImportError:
            pass

        if not portas:
            portas = ["COM3"]

        self.combo_porta.addItems(portas)

    def _carregar_configuracao(self) -> None:
        config = carregar()

        self._selecionar_combo(
            self.combo_porta,
            str(config.get("porta", "COM3")),
        )

        self._selecionar_combo(
            self.combo_baudrate,
            str(config.get("baudrate", 9600)),
        )

        paridade = str(config.get("paridade", "N")).upper()
        indice_paridade = self.combo_paridade.findData(paridade)

        if indice_paridade >= 0:
            self.combo_paridade.setCurrentIndex(indice_paridade)

        self._selecionar_combo(
            self.combo_stopbits,
            str(config.get("stopbits", 1)),
        )

        self.spin_slave.setValue(
            int(config.get("slave", 1))
        )

        self._selecionar_combo(
            self.combo_modo,
            str(config.get("modo", "SIMULADO")).upper(),
        )

    @staticmethod
    def _selecionar_combo(
        combo: QComboBox,
        valor: str,
    ) -> None:
        indice = combo.findText(valor)

        if indice >= 0:
            combo.setCurrentIndex(indice)
        else:
            combo.setCurrentText(valor)

    def _obter_configuracao(self) -> dict[str, object]:
        # Mescla os campos editáveis para preservar configurações avançadas.
        return mesclar_configuracao(carregar(), {
            "porta": self.combo_porta.currentText().strip(),
            "baudrate": int(self.combo_baudrate.currentText()),
            "slave": self.spin_slave.value(),
            "paridade": self.combo_paridade.currentData(),
            "stopbits": int(self.combo_stopbits.currentText()),
            "modo": self.combo_modo.currentText(),
        })

    def _salvar_configuracao(self) -> None:
        config = self._obter_configuracao()
        salvar(config)

        QMessageBox.information(
            self,
            "Configuração Modbus",
            "Configuração salva com sucesso.",
        )

    def _conectar(self) -> None:
        salvar(self._obter_configuracao())

        self.modbus.recarregar_configuracao()

        if self.modbus.conectar():
            self._atualizar_status()
            return

        self._atualizar_status()

        QMessageBox.warning(
            self,
            "Falha na conexão",
            self.modbus.ultimo_erro,
        )

    def _desconectar(self) -> None:
        self.modbus.desconectar()
        self._atualizar_status()

    def _atualizar_status(self) -> None:
        if self.modbus.conectado:
            texto = (
                f"● CONECTADO — {self.modbus.modo} — "
                f"{self.modbus.porta}"
            )
            cor = "#16853a"
        else:
            texto = "● DESCONECTADO"
            cor = "#c62828"

        self.label_status.setText(texto)
        self.label_status.setStyleSheet(
            f"""
            QLabel {{
                background: white;
                border: 1px solid #c6cfda;
                border-radius: 6px;
                color: {cor};
                font-weight: 800;
                padding: 8px;
            }}
            """
        )


def main() -> None:
    app = QApplication(sys.argv)
    janela = JanelaModbus()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
