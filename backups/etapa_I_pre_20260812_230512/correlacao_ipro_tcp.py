"""Snapshots e comparação; identifica candidatos, nunca confirma associações."""

from __future__ import annotations

from datetime import datetime

from leitor_ipro_tcp import LeituraTCP


def snapshot(nome: str, leituras: list[LeituraTCP]) -> dict:
    return {
        "nome": nome,
        "timestamp": datetime.now().astimezone().isoformat(),
        "leituras": [leitura.para_dict() for leitura in leituras],
    }


def comparar_snapshots(antes: dict, depois: dict) -> dict:
    def indexar(estado: dict) -> dict:
        resultado = {}
        for leitura in estado.get("leituras", []):
            chave = (leitura["unit_id"], leitura["funcao"], leitura["endereco"])
            for offset, valor in enumerate(leitura.get("valores_int16", [])):
                resultado[(*chave, offset)] = valor
        return resultado

    valores_a, valores_b = indexar(antes), indexar(depois)
    linhas = []
    for chave in sorted(set(valores_a) | set(valores_b)):
        a, b = valores_a.get(chave), valores_b.get(chave)
        linhas.append({
            "unit_id": chave[0], "funcao": chave[1], "endereco": chave[2],
            "offset": chave[3], "antes": a, "depois": b,
            "delta": b - a if a is not None and b is not None else None,
            "mudou": a != b,
            "classificacao": "CANDIDATO" if a != b else "DESCONHECIDO",
        })
    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        "antes": antes.get("nome"), "depois": depois.get("nome"),
        "classificacao_automatica": False,
        "linhas": linhas,
        "alteracoes": [linha for linha in linhas if linha["mudou"]],
    }
