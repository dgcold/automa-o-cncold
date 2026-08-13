import json
from pathlib import Path

from ipro_map import mapa_canais_serializavel


ARQUIVO = Path("config_modbus.json")


CONFIG_PADRAO = {
    "porta": "COM3",
    "baudrate": 9600,
    "slave": 1,
    "paridade": "N",
    "stopbits": 1,
    "modo": "SIMULADO",
    "tabela_registro": "holding",
    "offset_endereco": 0,
    "ordem_palavras": "big",
    "ordem_bytes": "big",
    "timeout": 1.0,
    "canais_ipro": mapa_canais_serializavel(),
}


def interpretar_booleano(valor, padrao=False):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        if normalizado in {"true", "1", "sim", "yes", "on"}:
            return True
        if normalizado in {"false", "0", "nao", "não", "no", "off", ""}:
            return False
    return bool(padrao)


def mesclar_configuracao(atual, alteracoes):
    return {**dict(atual), **dict(alteracoes)}


def carregar():

    if not ARQUIVO.exists():
        salvar(CONFIG_PADRAO)
        return CONFIG_PADRAO.copy()

    with open(
        ARQUIVO,
        "r",
        encoding="utf-8",
    ) as arquivo:

        carregada = json.load(arquivo)
        mesclada = {**CONFIG_PADRAO, **carregada}
        mesclada["canais_ipro"] = {
            **CONFIG_PADRAO["canais_ipro"],
            **carregada.get("canais_ipro", {}),
        }
        return mesclada


def salvar(config):

    with open(
        ARQUIVO,
        "w",
        encoding="utf-8",
    ) as arquivo:

        json.dump(
            config,
            arquivo,
            indent=4,
        )
