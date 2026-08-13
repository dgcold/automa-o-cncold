"""CLI auditável para conexão e leituras FC03/FC04 do iPro."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from correlacao_ipro_tcp import comparar_snapshots, snapshot
from leitor_ipro_tcp import LeitorIPRO_TCP


def registrar_jsonl(caminho: Path, evento: str, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps({
            "evento": evento,
            "registrado_em": datetime.now().astimezone().isoformat(),
            **dados,
        }, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico iPro Modbus TCP somente leitura")
    parser.add_argument("--host", default="192.168.0.250")
    parser.add_argument("--porta", type=int, default=502)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--endereco", type=int, default=0)
    parser.add_argument("--quantidade", type=int, default=1)
    parser.add_argument("--funcao", type=int, choices=(3, 4))
    parser.add_argument("--somente-conexao", action="store_true")
    parser.add_argument("--comparar", action="store_true",
                        help="captura dois estados de leitura sem alterar equipamento")
    parser.add_argument("--espera", type=float, default=5.0)
    args = parser.parse_args()
    leitor = LeitorIPRO_TCP(args.host, args.porta, args.timeout)
    pasta = Path(__file__).with_name("evidencias_tcp_ipro")
    evidencia = pasta / f"diagnostico_tcp_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    conexao = leitor.testar_conexao()
    registrar_jsonl(evidencia, "teste_conexao", conexao)
    print(json.dumps(conexao, ensure_ascii=False, indent=2))
    if conexao["status"] != "CONECTADO" or args.somente_conexao:
        print(f"Evidência: {evidencia}")
        return 0 if conexao["status"] == "CONECTADO" else 2

    funcoes = (args.funcao,) if args.funcao else (3, 4)
    requisicoes = tuple((args.unit_id, fc, args.endereco, args.quantidade) for fc in funcoes)
    antes = snapshot("ANTES", leitor.ler_varias(requisicoes))
    registrar_jsonl(evidencia, "estado_antes", antes)
    for leitura in antes["leituras"]:
        print(f"UNIT={leitura['unit_id']} FC={leitura['funcao']:02d} "
              f"END={leitura['endereco']} QTD={leitura['quantidade']} "
              f"STATUS={leitura['status']} VAL={leitura['valores_int16']} "
              f"TEMPO={leitura['tempo_resposta_ms']}ms ERRO={leitura['erro']}")
    if args.comparar:
        import time
        time.sleep(max(0.0, args.espera))
        depois = snapshot("DEPOIS", leitor.ler_varias(requisicoes))
        comparacao = comparar_snapshots(antes, depois)
        registrar_jsonl(evidencia, "estado_depois", depois)
        registrar_jsonl(evidencia, "comparacao", comparacao)
        print(f"Alterações candidatas: {len(comparacao['alteracoes'])}; confirmação automática: NÃO")
    print(f"Evidência: {evidencia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
