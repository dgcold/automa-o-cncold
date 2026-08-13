from __future__ import annotations

from dataclasses import dataclass

COMUNICACAO_OK = "OK"
COMUNICACAO_PARCIAL = "PARCIAL"
COMUNICACAO_DESCONECTADO = "DESCONECTADO"


def deve_usar_dados_reais(modo_fonte: str, possui_dados_reais: bool) -> bool:
    modo = str(modo_fonte).upper()
    return modo == "REAL" or (modo == "AUTO" and possui_dados_reais)


def controles_simulador_habilitados(modo_fonte: str) -> bool:
    return str(modo_fonte).upper() == "SIMULADO"


@dataclass(frozen=True)
class EstadoMaquina:
    modo: int
    nome_modo: str
    compressor: bool | None
    degelo: bool | None
    comunicacao: str
    alta_temperatura: bool
    alta_pressao: bool
    alta_temperatura_descarga: bool
    baixa_pressao: bool
    falha_sensor: bool
    comunicacao_perdida: bool
    alarmes: tuple[str, ...]

    @property
    def em_alarme(self) -> bool:
        return bool(self.alarmes)

    @property
    def falha_atual(self) -> str:
        return " | ".join(self.alarmes) if self.alarmes else "NENHUMA"

    @property
    def estado_compressor(self) -> str:
        if self.comunicacao_perdida:
            return "SEM COMUNICAÇÃO"
        if self.comunicacao == COMUNICACAO_PARCIAL:
            return "COMUNICAÇÃO PARCIAL"
        if self.em_alarme:
            return "FALHA"
        if self.degelo:
            return "DEGELO"
        if self.compressor:
            return "RESFRIANDO"
        return "PARADO"


def calcular_estado_maquina(
    gerador,
    *,
    modo_real: bool = False,
    comunicacao: str = COMUNICACAO_OK,
    compressor: bool | None = None,
    degelo: bool | None = None,
) -> EstadoMaquina:
    """Cria a única representação de estado consumida pela interface."""
    if not modo_real:
        comunicacao = COMUNICACAO_OK
        compressor = gerador.modo == 2
        degelo = gerador.modo == 3

    falha_explicita = gerador.nome_falha if gerador.modo == 4 else ""
    comunicacao_perdida = (
        (modo_real and comunicacao == COMUNICACAO_DESCONECTADO)
        or falha_explicita == "COMUNICAÇÃO MODBUS PERDIDA"
    )
    comunicacao_parcial = modo_real and comunicacao == COMUNICACAO_PARCIAL

    falha_sensor = (
        any(nome.startswith("FALHA DO SENSOR") for nome in gerador.alarmes_automaticos)
        or falha_explicita in {
            "TEMPERATURA CÂMARA ABERTA",
            "TEMPERATURA EVAPORADOR EM CURTO",
            "TRANSDUTOR SUCÇÃO ABERTO",
            "TRANSDUTOR DESCARGA EM CURTO",
        }
    )

    alarmes = list(gerador.alarmes_automaticos)
    if gerador.modo == 4:
        if falha_explicita not in alarmes:
            alarmes.append(falha_explicita)
    if comunicacao_perdida:
        alarmes.append("SEM COMUNICAÇÃO")
    elif comunicacao_parcial:
        alarmes.append("COMUNICAÇÃO PARCIAL")

    nome_modo = (
        "SEM COMUNICAÇÃO"
        if comunicacao_perdida
        else f"{gerador.nome_modo} — PARCIAL"
        if comunicacao_parcial
        else gerador.nome_modo
    )

    return EstadoMaquina(
        modo=gerador.modo,
        nome_modo=nome_modo,
        compressor=compressor,
        degelo=degelo,
        comunicacao=comunicacao,
        alta_temperatura=gerador.alarme_temp_camara,
        alta_pressao=(
            gerador.alarme_descarga
            or falha_explicita == "PRESSOSTATO DE ALTA ABERTO"
        ),
        alta_temperatura_descarga=(
            gerador.alarme_temp_descarga
            or falha_explicita == "TEMPERATURA DESCARGA ALTA"
        ),
        baixa_pressao=(
            gerador.alarme_succao
            or falha_explicita == "PRESSOSTATO DE BAIXA ABERTO"
        ),
        falha_sensor=falha_sensor,
        comunicacao_perdida=comunicacao_perdida,
        alarmes=tuple(dict.fromkeys(alarmes)),
    )
