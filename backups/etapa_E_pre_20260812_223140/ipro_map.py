from __future__ import annotations

from dataclasses import asdict, dataclass, replace


QUALIDADE_VALIDA = "VALIDA"
QUALIDADE_PROVISORIA = "PROVISORIA"
QUALIDADE_INVALIDA = "INVALIDA"
QUALIDADE_DESATUALIZADA = "DESATUALIZADA"
QUALIDADE_SEM_DADOS = "SEM_DADOS"


@dataclass(frozen=True)
class ConfiguracaoCanalIPro:
    endereco: int
    tipo: str
    trocar_bytes: bool
    escala: float
    offset: float
    unidade: str
    unidade_interface: str
    provisoria: bool = True
    minimo_fisico: float | None = None
    maximo_fisico: float | None = None


def decodificar_int16(valor_bruto: int, trocar_bytes: bool = False) -> int:
    """Decodifica somente o valor de um registrador INT16."""
    valor = int(valor_bruto) & 0xFFFF
    if trocar_bytes:
        valor = ((valor & 0x00FF) << 8) | ((valor & 0xFF00) >> 8)
    if valor >= 0x8000:
        valor -= 0x10000
    return valor


def aplicar_escala(valor_ordenado: int | float, escala: float, offset: float) -> float:
    return float(valor_ordenado) * float(escala) + float(offset)


# Mapa provisório: endereços, escalas e unidades ainda dependem de validação
# contra o display/documentação do iPro. A troca de bytes é deliberadamente
# individual; os endereços nunca passam por essa transformação.
IPRO_CANAIS: dict[str, ConfiguracaoCanalIPro] = {
    "temperatura_camara": ConfiguracaoCanalIPro(384, "int16", False, 1.0, 0.0, "°C?", "°C", True, -80.0, 100.0),
    "temperatura_evaporador": ConfiguracaoCanalIPro(388, "int16", True, 1.0, 0.0, "°C?", "°C", True, -80.0, 100.0),
    "temperatura_externa": ConfiguracaoCanalIPro(390, "int16", True, 1.0, 0.0, "°C?", "°C", True, -80.0, 100.0),
    "temperatura_insuflamento": ConfiguracaoCanalIPro(392, "int16", True, 1.0, 0.0, "°C?", "°C", True, -80.0, 100.0),
    "pressao_descarga_bar": ConfiguracaoCanalIPro(394, "int16", True, 1.0, 0.0, "bar?", "bar?", True, 0.0, 80.0),
    "pressao_succao_bar": ConfiguracaoCanalIPro(396, "int16", True, 1.0, 0.0, "bar?", "bar?", True, 0.0, 80.0),
    "temperatura_succao": ConfiguracaoCanalIPro(398, "int16", False, 1.0, 0.0, "°C?", "°C", True, -80.0, 150.0),
    "temperatura_liquido": ConfiguracaoCanalIPro(400, "int16", True, 1.0, 0.0, "°C?", "°C", True, -80.0, 150.0),
    "temperatura_descarga": ConfiguracaoCanalIPro(404, "int16", False, 1.0, 0.0, "°C?", "°C", True, -80.0, 250.0),
    "temperatura_condensacao": ConfiguracaoCanalIPro(406, "int16", False, 1.0, 0.0, "°C?", "°C", True, -80.0, 150.0),
    "temperatura_evaporacao": ConfiguracaoCanalIPro(407, "int16", False, 1.0, 0.0, "°C?", "°C", True, -80.0, 100.0),
    "superaquecimento": ConfiguracaoCanalIPro(408, "int16", False, 1.0, 0.0, "°C?", "°C", True, -50.0, 100.0),
    "subresfriamento": ConfiguracaoCanalIPro(409, "int16", True, 1.0, 0.0, "°C?", "°C", True, -50.0, 100.0),
    "capacidade_compressor": ConfiguracaoCanalIPro(896, "int16", False, 1.0, 0.0, "%?", "%", True, 0.0, 100.0),
    "capacidade_condensador": ConfiguracaoCanalIPro(897, "int16", False, 1.0, 0.0, "%?", "%", True, 0.0, 100.0),
    "abertura_valvula": ConfiguracaoCanalIPro(5424, "int16", True, 1.0, 0.0, "%?", "%", True, 0.0, 100.0),
    "unidade": ConfiguracaoCanalIPro(4096, "bool", False, 1.0, 0.0, "bool", "bool"),
    "compressor": ConfiguracaoCanalIPro(4864, "bool", False, 1.0, 0.0, "bool", "bool"),
    "condensador_1": ConfiguracaoCanalIPro(5120, "bool", False, 1.0, 0.0, "bool", "bool"),
    "condensador_2": ConfiguracaoCanalIPro(5125, "bool", False, 1.0, 0.0, "bool", "bool"),
    "evaporador": ConfiguracaoCanalIPro(5632, "bool", False, 1.0, 0.0, "bool", "bool"),
    "degelo": ConfiguracaoCanalIPro(5888, "bool", False, 1.0, 0.0, "bool", "bool"),
    "solenoide_liquido": ConfiguracaoCanalIPro(1128, "bool", False, 1.0, 0.0, "bool", "bool"),
}

IPRO_STATUS_PENDENTES_VALIDACAO = frozenset({4096, 4864, 5120, 5125, 5632, 5888})

# Compatibilidade com imports antigos; as configurações efetivas estão acima.
IPRO_ANALOGICOS_16 = {
    nome: canal.endereco for nome, canal in IPRO_CANAIS.items() if canal.tipo == "int16"
}
IPRO_STATUS = {
    nome: canal.endereco for nome, canal in IPRO_CANAIS.items() if canal.tipo == "bool"
}
IPRO_FLOATS: dict[str, int] = {}


def mapa_canais_serializavel() -> dict[str, dict[str, object]]:
    return {nome: asdict(config) for nome, config in IPRO_CANAIS.items()}


def configurar_canais(
    sobreposicoes: dict[str, dict[str, object]] | None,
) -> dict[str, ConfiguracaoCanalIPro]:
    resultado = dict(IPRO_CANAIS)
    for nome, campos in (sobreposicoes or {}).items():
        if nome not in resultado or not isinstance(campos, dict):
            continue
        valores = dict(campos)
        if "trocar_bytes" in valores and isinstance(valores["trocar_bytes"], str):
            valores["trocar_bytes"] = valores["trocar_bytes"].strip().lower() in {
                "true", "1", "sim", "yes", "on"
            }
        if "provisoria" in valores and isinstance(valores["provisoria"], str):
            valores["provisoria"] = valores["provisoria"].strip().lower() in {
                "true", "1", "sim", "yes", "on"
            }
        campos_validos = {
            chave: valor
            for chave, valor in valores.items()
            if chave in ConfiguracaoCanalIPro.__dataclass_fields__
        }
        resultado[nome] = replace(resultado[nome], **campos_validos)
    return resultado
