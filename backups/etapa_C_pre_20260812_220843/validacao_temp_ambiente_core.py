from __future__ import annotations

import socket
import struct
from datetime import datetime

from diagnostico_modbus_tcp_leitura import ler_resposta, montar_requisicao, validar_requisicao
from ipro_map import IPRO_CANAIS, aplicar_escala, decodificar_int16
from modbus_rs485 import ModbusRS485
from simulador_ipro_rs485 import crc16_modbus


PORTA = "COM8"
BAUDRATE = 9600
BYTESIZE = 8
PARIDADE = "N"
STOPBITS = 2
SLAVE = 1
FUNCAO = 4
ENDERECO = 10
QUANTIDADE = 6
ESCALA = 10.0
PASSOS_C = (20.0, 10.0, 0.0, -10.0, -20.0)
ESPERA_ATUALIZACAO_S = 15
RESULTADOS = (
    "CONFIRMADO POR TESTE DE BANCADA",
    "NÃO CONFIRMADO",
    "NÃO VALIDADO",
)

IPRO_TCP_HOST = "192.168.0.250"
IPRO_TCP_PORTA = 502
IPRO_TCP_TIMEOUT_S = 2.0
IPRO_TCP_UNIT_ID = 1
IPRO_TCP_FUNCAO = 4


class LeitorIPRO:
    def __init__(self, porta=None, baudrate=None, slave_id=None) -> None:
        self.modbus = ModbusRS485(
            porta=porta,
            baudrate=baudrate,
            slave_id=slave_id,
            simulado=False,
        )
        self.modbus.tabela_registro = "input"
        self.metodo = "Modbus RTU serial"
        self.mecanismo = "pymodbus.ModbusSerialClient"
        self.endereco_ip = None
        self.endpoint = f"serial://{self.modbus.porta}"

    def ler(self) -> dict[str, object]:
        if not self.modbus.conectado and not self.modbus.conectar():
            detalhes = {
                "metodo": self.metodo,
                "mecanismo": self.mecanismo,
                "endpoint": self.endpoint,
                "endereco_ip": self.endereco_ip or "COM-port serial",
                "porta": self.modbus.porta,
                "slave_id": self.modbus.slave_id,
                "tabela_registro": self.modbus.tabela_registro,
                "timeout_s": self.modbus.timeout,
                "erro_original": self.modbus.ultimo_erro,
            }
            raise RuntimeError(
                "Leitura iPro falhou na tentativa de conectar. "
                + "; ".join(f"{chave}={valor}" for chave, valor in detalhes.items())
            )

        try:
            return self.modbus.ler_ipro()
        except Exception as erro:
            erro_tipo = type(erro).__name__
            mensagem = str(erro)
            if "timed out" in mensagem.lower():
                classificacao = "timeout"
            elif "refused" in mensagem.lower() or "recusada" in mensagem.lower():
                classificacao = "conexao recusada"
            elif "crc" in mensagem.lower() or "modbus" in mensagem.lower():
                classificacao = "erro Modbus"
            else:
                classificacao = "outro erro"
            detalhes = {
                "metodo": self.metodo,
                "mecanismo": self.mecanismo,
                "endpoint": self.endpoint,
                "endereco_ip": self.endereco_ip or "COM-port serial",
                "porta": self.modbus.porta,
                "slave_id": self.modbus.slave_id,
                "tabela_registro": self.modbus.tabela_registro,
                "timeout_s": self.modbus.timeout,
                "erro_tipo": erro_tipo,
                "classificacao": classificacao,
                "erro_original": mensagem,
            }
            raise RuntimeError(
                "Leitura iPro falhou durante a leitura. "
                + "; ".join(f"{chave}={valor}" for chave, valor in detalhes.items())
            ) from erro

    def desconectar(self) -> None:
        self.modbus.desconectar()


class LeitorIPRO_TCP:
    def __init__(self, host: str = IPRO_TCP_HOST, porta: int = IPRO_TCP_PORTA) -> None:
        self.host = host
        self.porta = porta
        self.timeout = IPRO_TCP_TIMEOUT_S
        self.unit_id = IPRO_TCP_UNIT_ID
        self.funcao = IPRO_TCP_FUNCAO
        self.metodo = "Modbus TCP"
        self.mecanismo = "socket.create_connection"
        self.endpoint = f"tcp://{self.host}:{self.porta}"

    def _ler_registro(self, sock: socket.socket, transacao: int, endereco: int) -> int:
        validar_requisicao(self.unit_id, self.funcao, endereco, 1)
        requisicao = montar_requisicao(
            transacao,
            self.unit_id,
            self.funcao,
            endereco,
            1,
        )
        sock.sendall(requisicao)
        resposta = ler_resposta(sock, transacao, self.unit_id, self.funcao)
        if resposta["status"] != "OK":
            raise RuntimeError(
                f"Modbus TCP resposta inválida: {resposta['status']}"
            )
        return resposta["int16"][0]

    def ler(self) -> dict[str, object]:
        detalhes_erro: dict[str, object] = {
            "metodo": self.metodo,
            "mecanismo": self.mecanismo,
            "endpoint": self.endpoint,
            "ip": self.host,
            "porta": self.porta,
            "unit_id": self.unit_id,
            "funcao": self.funcao,
            "timeout_s": self.timeout,
        }
        try:
            with socket.create_connection((self.host, self.porta), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                transacao = 1
                dados: dict[str, object] = {}
                leituras: dict[str, dict[str, object]] = {}
                erros: list[str] = []

                for nome, canal in IPRO_CANAIS.items():
                    try:
                        bruto = self._ler_registro(sock, transacao, canal.endereco)
                        transacao = (transacao + 1) & 0xFFFF
                        if canal.tipo == "bool":
                            ordenado = int(bruto)
                            convertido = bool(ordenado)
                            escalado = convertido
                            plausivel = ordenado in (0, 1)
                        elif canal.tipo == "int16":
                            ordenado = decodificar_int16(bruto, canal.trocar_bytes)
                            escalado = aplicar_escala(ordenado, canal.escala, canal.offset)
                            convertido = escalado
                            plausivel = (
                                (canal.minimo_fisico is None or convertido >= canal.minimo_fisico)
                                and (canal.maximo_fisico is None or convertido <= canal.maximo_fisico)
                            )
                        else:
                            raise ValueError(f"Tipo de canal não suportado: {canal.tipo}")

                        qualidade = "VALIDA" if plausivel else "INVALIDA"
                        leitura = {
                            "endereco": canal.endereco,
                            "tipo": canal.tipo,
                            "valor_bruto": int(bruto),
                            "valor_ordenado": ordenado,
                            "valor_escalado": escalado,
                            "valor_convertido": convertido,
                            "valor": convertido,
                            "unidade_origem": canal.unidade,
                            "unidade_interface": canal.unidade_interface,
                            "qualidade": qualidade,
                        }
                        leituras[nome] = leitura
                        dados[nome] = convertido
                    except Exception as erro:
                        erros.append(f"{nome}@{canal.endereco}: {erro}")
                        leituras[nome] = {
                            "endereco": canal.endereco,
                            "tipo": canal.tipo,
                            "erro": str(erro),
                        }
                        dados[nome] = None

                dados["_leituras"] = leituras
                dados["_erros_leitura"] = erros
                dados["_comunicacao"] = "OK" if not erros else "PARCIAL"
                dados["_timestamp"] = datetime.now().astimezone().isoformat()
                return dados
        except (OSError, RuntimeError, ValueError) as erro:
            mensagem = str(erro)
            if "timed out" in mensagem.lower():
                classificacao = "timeout"
            elif "refused" in mensagem.lower() or "recusada" in mensagem.lower():
                classificacao = "conexao recusada"
            elif "modbus" in mensagem.lower():
                classificacao = "erro Modbus"
            else:
                classificacao = "outro erro"
            detalhes_erro.update({
                "erro_tipo": type(erro).__name__,
                "classificacao": classificacao,
                "erro_original": mensagem,
            })
            raise RuntimeError(
                "Leitura iPro TCP falhou. "
                + "; ".join(f"{chave}={valor}" for chave, valor in detalhes_erro.items())
            ) from erro

    def desconectar(self) -> None:
        pass


def comparar_estados_ipro(
    antes: dict[str, object],
    depois: dict[str, object],
) -> list[dict[str, object]]:
    linhas: list[dict[str, object]] = []
    chaves = sorted(
        chave
        for chave in set(antes) | set(depois)
        if not chave.startswith("_")
    )

    for chave in chaves:
        valor_antes = antes.get(chave)
        valor_depois = depois.get(chave)
        delta = None
        mudou = False

        if valor_antes is None or valor_depois is None:
            mudou = valor_antes != valor_depois
        elif isinstance(valor_antes, bool) or isinstance(valor_depois, bool):
            mudou = valor_antes != valor_depois
        elif isinstance(valor_antes, (int, float)) and isinstance(
            valor_depois, (int, float)
        ):
            delta = float(valor_depois) - float(valor_antes)
            mudou = abs(delta) > 1e-8
        else:
            mudou = valor_antes != valor_depois

        linhas.append({
            "nome": chave,
            "antes": valor_antes,
            "depois": valor_depois,
            "delta": delta,
            "mudou": mudou,
        })

    return linhas


def quadro_exato(frame: bytes) -> bool:
    if len(frame) != 8:
        return False
    if crc16_modbus(frame[:6]) != int.from_bytes(frame[6:8], "little"):
        return False
    return (
        frame[0] == SLAVE
        and frame[1] == FUNCAO
        and int.from_bytes(frame[2:4], "big") == ENDERECO
        and int.from_bytes(frame[4:6], "big") == QUANTIDADE
    )


def resposta_controlada(frame: bytes, bruto_assinado: int) -> tuple[bytes, list[int]] | None:
    """Responde somente à consulta autorizada; qualquer outra requisição é ignorada."""
    if not quadro_exato(frame):
        return None
    valores = [int(bruto_assinado) & 0xFFFF, 0, 0, 0, 0, 0]
    corpo = bytes([SLAVE, FUNCAO, QUANTIDADE * 2]) + b"".join(
        struct.pack(">H", valor) for valor in valores
    )
    return corpo + struct.pack("<H", crc16_modbus(corpo)), valores
