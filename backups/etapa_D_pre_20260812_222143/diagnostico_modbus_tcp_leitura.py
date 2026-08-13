"""Diagnóstico Modbus TCP estritamente somente leitura para o iPro.

Não contém implementação de FC05, FC06, FC15, FC16 ou qualquer escrita.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import struct
from datetime import datetime
from pathlib import Path


HOST_PADRAO = "192.168.0.250"
PORTA_PADRAO = 502
FUNCOES_PERMITIDAS = frozenset({3, 4})

# Endereços observados no simulador RS485. Os significados continuam desconhecidos.
REQUISICOES_RS485 = (
    (1, 4, 10, 6),
    (1, 4, 20, 1),
    (1, 4, 34, 1),
    (1, 4, 42, 1),
    (1, 4, 50, 1),
    (1, 4, 58, 1),
    (1, 4, 200, 1),
    (1, 4, 1200, 1),
    (1, 4, 1208, 1),
    (1, 4, 1216, 1),
    (2, 3, 256, 1),
    (2, 3, 261, 1),
    (2, 3, 263, 1),
    (2, 3, 272, 1),
    (2, 3, 3328, 1),
)


def validar_requisicao(unit_id: int, funcao: int, endereco: int, quantidade: int) -> None:
    if funcao not in FUNCOES_PERMITIDAS:
        raise ValueError("Somente FC03 e FC04 são permitidas.")
    if not 0 <= unit_id <= 247:
        raise ValueError("Unit ID deve estar entre 0 e 247.")
    if not 0 <= endereco <= 0xFFFF:
        raise ValueError("Endereço fora da faixa de 16 bits.")
    if not 1 <= quantidade <= 125:
        raise ValueError("Quantidade deve estar entre 1 e 125.")
    if endereco + quantidade - 1 > 0xFFFF:
        raise ValueError("A leitura ultrapassa o endereço 65535.")


def montar_requisicao(
    transacao: int, unit_id: int, funcao: int, endereco: int, quantidade: int
) -> bytes:
    validar_requisicao(unit_id, funcao, endereco, quantidade)
    # MBAP: transação, protocolo=0, comprimento=6; PDU: FC, endereço, quantidade.
    return struct.pack(
        ">HHHBBHH", transacao & 0xFFFF, 0, 6,
        unit_id, funcao, endereco, quantidade,
    )


def receber_exato(sock: socket.socket, quantidade: int) -> bytes:
    partes = bytearray()
    while len(partes) < quantidade:
        parte = sock.recv(quantidade - len(partes))
        if not parte:
            raise ConnectionError("Conexão encerrada antes da resposta completa.")
        partes.extend(parte)
    return bytes(partes)


def ler_resposta(sock: socket.socket, transacao: int, unit_id: int, funcao: int) -> dict:
    mbap = receber_exato(sock, 7)
    transacao_resp, protocolo, comprimento, unit_resp = struct.unpack(">HHHB", mbap)
    if protocolo != 0 or transacao_resp != (transacao & 0xFFFF):
        raise ValueError("Cabeçalho MBAP inesperado.")
    if comprimento < 2 or comprimento > 254:
        raise ValueError(f"Comprimento MBAP inválido: {comprimento}.")
    pdu = receber_exato(sock, comprimento - 1)
    funcao_resp = pdu[0]
    bruto = mbap + pdu
    if funcao_resp == (funcao | 0x80):
        codigo = pdu[1] if len(pdu) > 1 else None
        return {"status": "EXCECAO", "codigo_excecao": codigo,
                "registros": [], "resposta_hex": bruto.hex(" ").upper()}
    if funcao_resp != funcao or unit_resp != unit_id:
        raise ValueError("Unit ID ou função divergente na resposta.")
    if len(pdu) < 2 or pdu[1] != len(pdu) - 2 or pdu[1] % 2:
        raise ValueError("Contagem de bytes inválida na resposta.")
    registros = [
        int.from_bytes(pdu[indice:indice + 2], "big")
        for indice in range(2, len(pdu), 2)
    ]
    assinados = [valor - 65536 if valor >= 32768 else valor for valor in registros]
    return {"status": "OK", "codigo_excecao": None,
            "registros": registros, "int16": assinados,
            "resposta_hex": bruto.hex(" ").upper()}


def executar_leituras(host: str, porta: int, timeout: float,
                      requisicoes: tuple[tuple[int, int, int, int], ...]) -> list[dict]:
    resultados = []
    with socket.create_connection((host, porta), timeout=timeout) as sock:
        sock.settimeout(timeout)
        for transacao, (unit_id, funcao, endereco, quantidade) in enumerate(requisicoes, 1):
            pedido = montar_requisicao(transacao, unit_id, funcao, endereco, quantidade)
            registro = {
                "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "host": host, "porta": porta, "unit_id": unit_id,
                "funcao": funcao, "endereco": endereco, "quantidade": quantidade,
                "requisicao_hex": pedido.hex(" ").upper(),
            }
            try:
                sock.sendall(pedido)
                resposta = ler_resposta(sock, transacao, unit_id, funcao)
                registro.update(resposta)
            except (OSError, ValueError, ConnectionError) as erro:
                registro.update({"status": "ERRO", "erro": str(erro),
                                 "registros": [], "int16": []})
            resultados.append(registro)
            print(
                f"UNIT={unit_id} FC={funcao:02d} END={endereco} QTD={quantidade} "
                f"STATUS={registro['status']} VAL={registro.get('int16', [])}"
            )
    return resultados


def salvar_resultados(resultados: list[dict], pasta: Path) -> tuple[Path, Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = pasta / f"modbus_tcp_leitura_{sufixo}.json"
    csv_path = pasta / f"modbus_tcp_leitura_{sufixo}.csv"
    with json_path.open("w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, indent=2, ensure_ascii=False)
    campos = ("timestamp", "host", "porta", "unit_id", "funcao", "endereco",
              "quantidade", "status", "codigo_excecao", "registros", "int16",
              "requisicao_hex", "resposta_hex", "erro")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";",
                                  extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(resultados)
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnóstico SOMENTE LEITURA Modbus TCP do iPro (FC03/FC04)."
    )
    parser.add_argument("--host", default=HOST_PADRAO)
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--saida", type=Path,
        default=Path(__file__).with_name("diagnosticos_modbus_tcp"),
    )
    args = parser.parse_args()
    print(f"Conectando a {args.host}:{args.porta} — SOMENTE FC03/FC04")
    resultados = executar_leituras(
        args.host, args.porta, args.timeout, REQUISICOES_RS485
    )
    json_path, csv_path = salvar_resultados(resultados, args.saida)
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
