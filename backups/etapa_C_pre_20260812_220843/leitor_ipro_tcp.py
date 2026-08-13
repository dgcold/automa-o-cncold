"""Cliente Modbus TCP do iPro estritamente somente leitura (FC03/FC04)."""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable


FUNCOES_LEITURA = frozenset({3, 4})
FUNCOES_ESCRITA_BLOQUEADAS = frozenset({5, 6, 15, 16})


@dataclass(frozen=True)
class LeituraTCP:
    timestamp: str
    ip: str
    porta: int
    unit_id: int
    funcao: int
    endereco: int
    quantidade: int
    status: str
    valores_uint16: list[int]
    valores_int16: list[int]
    requisicao_hex: str
    resposta_hex: str
    tempo_resposta_ms: float | None
    codigo_excecao: int | None = None
    erro_tipo: str | None = None
    erro: str | None = None
    classificacao: str = "NÃO VALIDADO"
    observacao_operador: str | None = None

    def para_dict(self) -> dict:
        return asdict(self)


class LeitorIPRO_TCP:
    def __init__(self, host: str = "192.168.0.250", porta: int = 502,
                 timeout: float = 2.0) -> None:
        self.host = host
        self.porta = int(porta)
        self.timeout = float(timeout)
        self.endpoint = f"tcp://{host}:{porta}"
        self._transacao = 0

    @staticmethod
    def validar_leitura(unit_id: int, funcao: int, endereco: int,
                        quantidade: int) -> None:
        if funcao not in FUNCOES_LEITURA:
            if funcao in FUNCOES_ESCRITA_BLOQUEADAS:
                raise PermissionError(f"FC{funcao:02d} bloqueada: escrita não permitida.")
            raise PermissionError("Somente FC03 e FC04 são permitidas.")
        if not 0 <= unit_id <= 247:
            raise ValueError("Unit ID deve estar entre 0 e 247.")
        if not 0 <= endereco <= 65535:
            raise ValueError("Endereço deve estar entre 0 e 65535.")
        if not 1 <= quantidade <= 125 or endereco + quantidade > 65536:
            raise ValueError("Quantidade/endereço fora da faixa Modbus.")

    def testar_conexao(self) -> dict:
        inicio = time.perf_counter()
        try:
            with socket.create_connection((self.host, self.porta), self.timeout):
                return {
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "endpoint": self.endpoint,
                    "status": "CONECTADO",
                    "latencia_ms": round((time.perf_counter() - inicio) * 1000, 3),
                    "erro_tipo": None,
                    "erro": None,
                }
        except OSError as erro:
            return {
                "timestamp": datetime.now().astimezone().isoformat(),
                "endpoint": self.endpoint,
                "status": "ERRO",
                "latencia_ms": round((time.perf_counter() - inicio) * 1000, 3),
                "erro_tipo": type(erro).__name__,
                "erro": repr(erro),
            }

    def _proxima_transacao(self) -> int:
        self._transacao = (self._transacao + 1) & 0xFFFF
        return self._transacao

    @staticmethod
    def _receber(sock: socket.socket, quantidade: int) -> bytes:
        dados = bytearray()
        while len(dados) < quantidade:
            parte = sock.recv(quantidade - len(dados))
            if not parte:
                raise ConnectionError("Conexão encerrada antes da resposta completa.")
            dados.extend(parte)
        return bytes(dados)

    def ler(self, unit_id: int, funcao: int, endereco: int,
            quantidade: int) -> LeituraTCP:
        self.validar_leitura(unit_id, funcao, endereco, quantidade)
        transacao = self._proxima_transacao()
        requisicao = struct.pack(">HHHBBHH", transacao, 0, 6, unit_id,
                                  funcao, endereco, quantidade)
        inicio = time.perf_counter()
        timestamp = datetime.now().astimezone().isoformat()
        try:
            with socket.create_connection((self.host, self.porta), self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(requisicao)
                mbap = self._receber(sock, 7)
                tx, protocolo, comprimento, unit_resp = struct.unpack(">HHHB", mbap)
                if tx != transacao or protocolo != 0 or unit_resp != unit_id:
                    raise ValueError("Cabeçalho MBAP divergente da requisição.")
                if not 2 <= comprimento <= 254:
                    raise ValueError(f"Comprimento MBAP inválido: {comprimento}.")
                pdu = self._receber(sock, comprimento - 1)
                resposta = mbap + pdu
                latencia = round((time.perf_counter() - inicio) * 1000, 3)
                if pdu[0] == (funcao | 0x80):
                    codigo = pdu[1] if len(pdu) > 1 else None
                    return LeituraTCP(timestamp, self.host, self.porta, unit_id,
                        funcao, endereco, quantidade, "EXCECAO_MODBUS", [], [],
                        requisicao.hex(" ").upper(), resposta.hex(" ").upper(),
                        latencia, codigo_excecao=codigo)
                if pdu[0] != funcao or len(pdu) < 2 or pdu[1] != len(pdu) - 2:
                    raise ValueError("PDU de resposta inválida.")
                valores = [int.from_bytes(pdu[i:i + 2], "big")
                           for i in range(2, len(pdu), 2)]
                if len(valores) != quantidade:
                    raise ValueError("Quantidade de registros divergente.")
                assinados = [v - 65536 if v >= 32768 else v for v in valores]
                return LeituraTCP(timestamp, self.host, self.porta, unit_id,
                    funcao, endereco, quantidade, "OK", valores, assinados,
                    requisicao.hex(" ").upper(), resposta.hex(" ").upper(), latencia)
        except (OSError, ValueError, ConnectionError) as erro:
            return LeituraTCP(timestamp, self.host, self.porta, unit_id, funcao,
                endereco, quantidade, "ERRO", [], [],
                requisicao.hex(" ").upper(), "",
                round((time.perf_counter() - inicio) * 1000, 3),
                erro_tipo=type(erro).__name__, erro=repr(erro))

    def ler_varias(self, requisicoes: Iterable[tuple[int, int, int, int]]) -> list[LeituraTCP]:
        return [self.ler(*requisicao) for requisicao in requisicoes]
