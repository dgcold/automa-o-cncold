"""Varredura somente leitura e correlação contra W1 atual do iPro."""

from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from leitor_ipro_tcp import LeitorIPRO_TCP


W1_NOMES = {
    0: "Temperatura Ambiente", 4: "Temperatura de Degelo",
    6: "Temperatura Externa", 8: "Temperatura de Descarga",
    10: "Pressão de Descarga", 13: "Pressão de Sucção",
    15: "Temperatura de Insuflamento", 17: "Temperatura de Sucção",
    19: "Temperatura de Líquido", 23: "Temperatura de Evaporação",
    24: "Superaquecimento", 25: "Sub-resfriamento", 26: "Setpoint Temperatura",
    39: "Status Unidade", 41: "Status Evaporador", 44: "Status Compressor",
    47: "Capacidade Compressor", 50: "Status Condensador 1",
    53: "Capacidade Condensador 1", 54: "Abertura VEE",
    55: "Capacidade Condensador 2", 56: "Status Degelo",
    66: "Status Solenoide", 71: "Status Condensador 2",
}


def int16(valor: int) -> int:
    return valor - 65536 if valor >= 32768 else valor


def trocar_bytes(valor: int) -> int:
    return ((valor & 255) << 8) | ((valor >> 8) & 255)


def obter_w1(host: str, timeout: float) -> list[int]:
    nome = urllib.parse.quote("W1")
    url = f"http://{host}/cgi-bin/xjgetvar.cgi?name={nome}"
    with urllib.request.urlopen(url, timeout=timeout) as resposta:
        objeto = json.loads(resposta.read().decode("utf-8"))
    return [int(v) for v in objeto["values"][0]["value"]]


def pontuar_janela(valores: list[int], w1: list[int]) -> tuple[int, int, list[int]]:
    limite = min(len(valores), len(w1))
    diretos = [int16(v) for v in valores[:limite]]
    trocados = [int16(trocar_bytes(v)) for v in valores[:limite]]
    pontos_direto = sum(a == b for a, b in zip(diretos, w1))
    pontos_trocado = sum(a == b for a, b in zip(trocados, w1))
    if pontos_trocado > pontos_direto:
        return pontos_trocado, 1, trocados
    return pontos_direto, 0, diretos


def main() -> int:
    p = argparse.ArgumentParser(description="Varredura Modbus TCP FC03/FC04 somente leitura")
    p.add_argument("--host", default="192.168.0.250")
    p.add_argument("--unit-id", type=int, default=1)
    p.add_argument("--inicio", type=int, default=0)
    p.add_argument("--fim", type=int, default=8191)
    p.add_argument("--bloco", type=int, default=64)
    p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--w1-cache", type=Path)
    args = p.parse_args()
    if args.w1_cache:
        w1 = [int(v) for v in json.loads(
            args.w1_cache.read_text(encoding="utf-8"))["w1"]]
    else:
        w1 = obter_w1(args.host, args.timeout)
    leitor = LeitorIPRO_TCP(args.host, 502, args.timeout)
    pasta = Path(__file__).with_name("evidencias_tcp_ipro")
    pasta.mkdir(exist_ok=True)
    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = pasta / f"varredura_{args.inicio}_{args.fim}_{sufixo}.json"
    csv_path = pasta / f"candidatos_{args.inicio}_{args.fim}_{sufixo}.csv"
    memoria: dict[int, dict[int, int]] = {3: {}, 4: {}}
    leituras = []
    total = ((args.fim - args.inicio + 1 + args.bloco - 1) // args.bloco) * 2
    atual = 0
    for fc in (3, 4):
        endereco = args.inicio
        while endereco <= args.fim:
            quantidade = min(args.bloco, args.fim - endereco + 1)
            leitura = leitor.ler(args.unit_id, fc, endereco, quantidade)
            registro = leitura.para_dict()
            leituras.append(registro)
            if leitura.status == "OK":
                for offset, valor in enumerate(leitura.valores_uint16):
                    memoria[fc][endereco + offset] = valor
            atual += 1
            print(f"[{atual}/{total}] FC{fc:02d} {endereco}-{endereco+quantidade-1}: {leitura.status}")
            endereco += quantidade

    janelas = []
    for fc in (3, 4):
        for inicio in range(args.inicio, args.fim - len(w1) + 2):
            if not all(inicio + i in memoria[fc] for i in range(len(w1))):
                continue
            valores = [memoria[fc][inicio + i] for i in range(len(w1))]
            pontos, swap, decodificados = pontuar_janela(valores, w1)
            janelas.append({"fc": fc, "inicio": inicio, "acertos": pontos,
                            "total_w1": len(w1), "troca_bytes": bool(swap)})
    janelas.sort(key=lambda x: (-x["acertos"], x["fc"], x["inicio"]))

    candidatos = []
    for indice, nome in W1_NOMES.items():
        alvo = w1[indice]
        for fc in (3, 4):
            for endereco, raw in memoria[fc].items():
                for ordem, valor in (("normal", int16(raw)),
                                     ("bytes_trocados", int16(trocar_bytes(raw)))):
                    if valor == alvo:
                        candidatos.append({
                            "w1": indice, "variavel": nome, "valor_ipro": alvo,
                            "fc": fc, "endereco": endereco, "valor_bruto": raw,
                            "valor_int16": valor, "ordem": ordem,
                            "escala": "÷10" if indice in {0,4,6,8,10,13,15,17,19,23,24,25,26} else "estado",
                            "confianca": "CANDIDATO",
                        })
    with json_path.open("w", encoding="utf-8") as arq:
        json.dump({"timestamp": datetime.now().astimezone().isoformat(),
            "host": args.host, "porta": 502, "unit_id": args.unit_id,
            "funcoes": [3, 4], "faixa": [args.inicio, args.fim], "w1": w1,
            "leituras": leituras, "melhores_janelas": janelas[:50],
            "candidatos": candidatos, "confirmacao_automatica": False},
            arq, ensure_ascii=False, indent=2)
    campos = ("w1","variavel","valor_ipro","fc","endereco","valor_bruto",
              "valor_int16","ordem","escala","confianca")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as arq:
        escritor = csv.DictWriter(arq, fieldnames=campos, delimiter=";")
        escritor.writeheader(); escritor.writerows(candidatos)
    print("MELHORES JANELAS W1:")
    for item in janelas[:20]: print(item)
    print(f"JSON={json_path}")
    print(f"CSV={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
