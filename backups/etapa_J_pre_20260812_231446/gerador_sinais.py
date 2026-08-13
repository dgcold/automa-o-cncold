from __future__ import annotations

import copy
import csv
import random
from datetime import datetime
from pathlib import Path

from canais import CANAIS
from refrigerantes import calcular_subresfriamento_c, calcular_superaquecimento_c

ARQUIVO_HISTORICO = "historico_gerador_refrigeracao.csv"

TEMP_CAMARA_ALTA_ON = 40.0
TEMP_CAMARA_ALTA_OFF = 35.0
PRESSAO_DESCARGA_ALTA_ON = 450.0
PRESSAO_DESCARGA_ALTA_OFF = 400.0
PRESSAO_SUCCAO_BAIXA_ON = 5.0
PRESSAO_SUCCAO_BAIXA_OFF = 10.0
TEMP_DESCARGA_ALTA_ON = 120.0
TEMP_DESCARGA_ALTA_OFF = 105.0

# Dinâmica térmica da simulação
TEMPERATURA_AMBIENTE = 25.0
SETPOINT_CAMARA = -18.0
DIFERENCIAL_CAMARA = 2.0
TEMPO_FASE_INICIAL_DEGELO = 30.0
TEMPO_FASE_INTERMEDIARIA_DEGELO = 90.0

# Rampa do compressor após o degelo
CAPACIDADE_INICIAL_POS_DEGELO = 30.0
TEMPO_RAMPA_POS_DEGELO = 60.0


def aproximar(valor_atual: float, valor_alvo: float, velocidade: float, tempo: float) -> float:
    return valor_atual + (valor_alvo - valor_atual) * velocidade * tempo


def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


class GeradorRefrigeracao:
    MODOS = {
        1: "MÁQUINA PARADA",
        2: "RESFRIAMENTO",
        3: "DEGELO",
        4: "FALHA DE SENSOR",
    }

    FALHAS = {
        1: "TEMPERATURA CÂMARA ABERTA",
        2: "TEMPERATURA EVAPORADOR EM CURTO",
        3: "TRANSDUTOR SUCÇÃO ABERTO",
        4: "TRANSDUTOR DESCARGA EM CURTO",
        5: "TEMPERATURA DESCARGA ALTA",
        6: "ALTA PRESSÃO DE DESCARGA",
        7: "BAIXA PRESSÃO DE SUCÇÃO",
        8: "PRESSOSTATO DE ALTA ABERTO",
        9: "PRESSOSTATO DE BAIXA ABERTO",
        10: "COMUNICAÇÃO MODBUS PERDIDA",
    }

    def __init__(self) -> None:
        self.modo = 1
        self.agressividade = 20
        self.pausado = False
        self.refrigerante = "R404A"
        self.tempo_no_modo = 0.0

        self.pos_degelo_ativo = False
        self.tempo_pos_degelo = 0.0

        self.canais = copy.deepcopy(CANAIS)
        self.camara = self.canais[0]
        self.evaporador = self.canais[1]
        self.succao = self.canais[2]
        self.descarga = self.canais[3]
        self.temperatura_descarga = self.canais[4]
        self.temperatura_succao = self.canais[5]
        self.temperatura_liquido = self.canais[6]

        self.modo_manual_temperaturas = False
        self.valores_manuais = self._valores_atuais()
        self.numero_falha = 1
        self.valores_normais: dict[str, float] = {}

        self.alarme_temp_camara = False
        self.alarme_descarga = False
        self.alarme_succao = False
        self.alarme_temp_descarga = False
        self.alarmes_automaticos: list[str] = []
        self.em_alarme_automatico = False

    @property
    def nome_modo(self) -> str:
        return self.MODOS[self.modo]

    @property
    def nome_falha(self) -> str:
        return self.FALHAS[self.numero_falha]

    @property
    def superaquecimento(self) -> float | None:
        valor, _ = calcular_superaquecimento_c(
            self.succao.valor,
            self.temperatura_succao.valor,
            self.refrigerante,
        )
        return valor

    @property
    def subresfriamento(self) -> float | None:
        valor, _ = calcular_subresfriamento_c(
            self.descarga.valor,
            self.temperatura_liquido.valor,
            self.refrigerante,
        )
        return valor

    @property
    def temperatura_saturacao_succao(self) -> float | None:
        _, temperatura = calcular_superaquecimento_c(
            self.succao.valor,
            self.temperatura_succao.valor,
            self.refrigerante,
        )
        return temperatura

    @property
    def temperatura_saturacao_condensacao(self) -> float | None:
        _, temperatura = calcular_subresfriamento_c(
            self.descarga.valor,
            self.temperatura_liquido.valor,
            self.refrigerante,
        )
        return temperatura

    @property
    def nome_alarme_automatico(self) -> str:
        return self.alarmes_automaticos[0] if self.alarmes_automaticos else "NENHUMA"

    @property
    def capacidade_compressor_percentual(self) -> float:
        """Capacidade efetiva do compressor, incluindo a rampa pós-degelo."""
        alvo = float(self.agressividade)

        if not self.pos_degelo_ativo:
            return limitar(alvo, 0.0, 100.0)

        progresso = limitar(
            self.tempo_pos_degelo / TEMPO_RAMPA_POS_DEGELO,
            0.0,
            1.0,
        )

        capacidade = (
            CAPACIDADE_INICIAL_POS_DEGELO
            + (alvo - CAPACIDADE_INICIAL_POS_DEGELO) * progresso
        )

        return limitar(capacidade, 0.0, 100.0)

    def selecionar_refrigerante(self, refrigerante: str) -> None:
        self.refrigerante = refrigerante

    def selecionar_modo(self, modo: int) -> None:
        if modo not in self.MODOS:
            return

        modo_anterior = self.modo

        if modo_anterior == 4 and modo != 4:
            self._restaurar_valores_normais()

        if modo != modo_anterior:
            self.tempo_no_modo = 0.0

        # Ao sair do degelo para resfriamento, inicia em 30%
        # e sobe gradualmente até a agressividade selecionada.
        if modo_anterior == 3 and modo == 2:
            self.pos_degelo_ativo = True
            self.tempo_pos_degelo = 0.0
        elif modo != 2:
            self.pos_degelo_ativo = False
            self.tempo_pos_degelo = 0.0

        self.modo = modo

        if modo == 4:
            self._salvar_valores_normais()

    def proxima_falha(self) -> None:
        self._restaurar_valores_normais()
        self.numero_falha = 1 if self.numero_falha >= len(self.FALHAS) else self.numero_falha + 1
        self._salvar_valores_normais()

    def aumentar_agressividade(self) -> None:
        self.agressividade = min(100, self.agressividade + 10)

    def diminuir_agressividade(self) -> None:
        self.agressividade = max(0, self.agressividade - 10)

    def ativar_modo_manual_temperaturas(self, ativo: bool) -> None:
        self.modo_manual_temperaturas = ativo
        if ativo:
            self.valores_manuais = self._valores_atuais()

    def definir_temperatura_manual(self, nome: str, valor: float) -> None:
        if nome in self.valores_manuais:
            self.valores_manuais[nome] = float(valor)

    def resetar(self) -> None:
        self.__init__()

    def atualizar(self, tempo_decorrido: float) -> None:
        if self.pausado:
            return

        tempo_decorrido = max(0.0, min(float(tempo_decorrido), 2.0))
        self.tempo_no_modo += tempo_decorrido

        if self.pos_degelo_ativo and self.modo == 2:
            self.tempo_pos_degelo += tempo_decorrido

            if self.tempo_pos_degelo >= TEMPO_RAMPA_POS_DEGELO:
                self.pos_degelo_ativo = False

        fator = 1.0 + self.capacidade_compressor_percentual / 100.0
        {
            1: self._atualizar_parada,
            2: self._atualizar_resfriamento,
            3: self._atualizar_degelo,
            4: self._atualizar_falha,
        }[self.modo](tempo_decorrido, fator)
        self._aplicar_valores_manuais()
        self._aplicar_limites()
        self._avaliar_alarmes_automaticos()

    def _valores_atuais(self) -> dict[str, float]:
        return {
            "camara": self.camara.valor,
            "evaporador": self.evaporador.valor,
            "succao": self.succao.valor,
            "descarga": self.descarga.valor,
            "temperatura_descarga": self.temperatura_descarga.valor,
            "linha_succao": self.temperatura_succao.valor,
            "linha_liquido": self.temperatura_liquido.valor,
        }

    def _aplicar_valores_manuais(self) -> None:
        if not self.modo_manual_temperaturas:
            return
        self.camara.valor = self.valores_manuais["camara"]
        self.evaporador.valor = self.valores_manuais["evaporador"]
        self.succao.valor = self.valores_manuais["succao"]
        self.descarga.valor = self.valores_manuais["descarga"]
        self.temperatura_descarga.valor = self.valores_manuais["temperatura_descarga"]
        self.temperatura_succao.valor = self.valores_manuais["linha_succao"]
        self.temperatura_liquido.valor = self.valores_manuais["linha_liquido"]

    def _salvar_valores_normais(self) -> None:
        self.valores_normais = self._valores_atuais()

    def _restaurar_valores_normais(self) -> None:
        if not self.valores_normais:
            return
        for chave, valor in self.valores_normais.items():
            alvo = {
                "camara": self.camara,
                "evaporador": self.evaporador,
                "succao": self.succao,
                "descarga": self.descarga,
                "temperatura_descarga": self.temperatura_descarga,
                "linha_succao": self.temperatura_succao,
                "linha_liquido": self.temperatura_liquido,
            }[chave]
            alvo.valor = valor

    def _atualizar_parada(self, tempo: float, fator: float) -> None:
        """Equaliza pressões e aproxima temperaturas do ambiente lentamente."""
        self.camara.valor = aproximar(
            self.camara.valor,
            TEMPERATURA_AMBIENTE,
            0.004,
            tempo,
        )

        self.evaporador.valor = aproximar(
            self.evaporador.valor,
            self.camara.valor - 0.4,
            0.035,
            tempo,
        )

        self.temperatura_succao.valor = aproximar(
            self.temperatura_succao.valor,
            self.evaporador.valor + 1.5,
            0.040,
            tempo,
        )

        self.temperatura_liquido.valor = aproximar(
            self.temperatura_liquido.valor,
            TEMPERATURA_AMBIENTE,
            0.035,
            tempo,
        )

        # Equalização lenta das pressões durante a parada
        self.succao.valor = aproximar(
            self.succao.valor,
            95.0,
            0.012,
            tempo,
        )

        self.descarga.valor = aproximar(
            self.descarga.valor,
            95.0,
            0.012,
            tempo,
        )

        self.temperatura_descarga.valor = aproximar(
            self.temperatura_descarga.valor,
            self.camara.valor + 2.0,
            0.050,
            tempo,
        )

        self._aplicar_ruido_suave(0.25)

    def _atualizar_resfriamento(self, tempo: float, fator: float) -> None:
        """Resfriamento com inércia térmica e transições suaves."""
        intensidade = self.capacidade_compressor_percentual / 100.0

        # A carga térmica diminui conforme a câmara se aproxima do setpoint.
        faixa_total = max(1.0, TEMPERATURA_AMBIENTE - SETPOINT_CAMARA)
        carga_termica = limitar(
            (self.camara.valor - SETPOINT_CAMARA) / faixa_total,
            0.08,
            1.0,
        )

        # Queda mais rápida com a câmara quente e mais lenta perto do setpoint.
        queda_c_por_minuto = (
            0.35
            + 1.65 * carga_termica
        ) * (0.65 + 0.70 * intensidade)

        if self.camara.valor > SETPOINT_CAMARA:
            self.camara.valor -= (
                queda_c_por_minuto / 60.0
            ) * tempo * fator
        else:
            self.camara.valor = aproximar(
                self.camara.valor,
                SETPOINT_CAMARA,
                0.010,
                tempo,
            )

        # Pressões variam de forma progressiva, sem saltos.
        # Calibração final das pressões
        alvo_succao = 20.0 - 7.0 * intensidade
        alvo_descarga = 235.0 + 30.0 * intensidade

        self.succao.valor = aproximar(
            self.succao.valor,
            alvo_succao,
            0.038 * fator,
            tempo,
        )

        self.descarga.valor = aproximar(
            self.descarga.valor,
            alvo_descarga,
            0.034 * fator,
            tempo,
        )

        temperatura_evaporacao = self.temperatura_saturacao_succao
        if temperatura_evaporacao is None:
            temperatura_evaporacao = self.camara.valor - 12.0

        # Evaporador acompanha a evaporação com inércia.
        alvo_evaporador = temperatura_evaporacao + 6.0
        self.evaporador.valor = aproximar(
            self.evaporador.valor,
            alvo_evaporador,
            0.050 * fator,
            tempo,
        )

        # Mantém superaquecimento próximo de 8 °C.
        alvo_temperatura_succao = temperatura_evaporacao + 8.0
        self.temperatura_succao.valor = aproximar(
            self.temperatura_succao.valor,
            alvo_temperatura_succao,
            0.065 * fator,
            tempo,
        )

        temperatura_condensacao = self.temperatura_saturacao_condensacao
        if temperatura_condensacao is None:
            temperatura_condensacao = 40.0

        # Mantém sub-resfriamento próximo de 5 °C.
        alvo_temperatura_liquido = temperatura_condensacao - 5.0
        self.temperatura_liquido.valor = aproximar(
            self.temperatura_liquido.valor,
            alvo_temperatura_liquido,
            0.055 * fator,
            tempo,
        )

        # Temperatura de descarga mais próxima da operação real
        alvo_temperatura_descarga = 78.0 + 22.0 * intensidade
        self.temperatura_descarga.valor = aproximar(
            self.temperatura_descarga.valor,
            alvo_temperatura_descarga,
            0.040 * fator,
            tempo,
        )

        self._aplicar_ruido_suave(1.0)
        self._aplicar_picos_suaves()

    def _atualizar_degelo(self, tempo: float, fator: float) -> None:
        """Degelo por gás quente em três fases, com inércia térmica."""
        intensidade = self.agressividade / 100.0

        if self.tempo_no_modo <= TEMPO_FASE_INICIAL_DEGELO:
            # Fase 1: evaporador sobe rápido; câmara quase não muda.
            alvo_evaporador = 0.0
            velocidade_evaporador = 0.085 * fator
            aquecimento_camara = 0.03 / 60.0

        elif self.tempo_no_modo <= TEMPO_FASE_INTERMEDIARIA_DEGELO:
            # Fase 2: gelo derretendo; evaporador busca temperatura positiva.
            alvo_evaporador = 8.0 + 3.0 * intensidade
            velocidade_evaporador = 0.070 * fator
            aquecimento_camara = 0.10 / 60.0

        else:
            # Fase 3: final do degelo; estabilização entre 10 e 15 °C.
            alvo_evaporador = 11.0 + 4.0 * intensidade
            velocidade_evaporador = 0.045 * fator
            aquecimento_camara = 0.18 / 60.0

        self.camara.valor += aquecimento_camara * tempo * fator

        self.evaporador.valor = aproximar(
            self.evaporador.valor,
            alvo_evaporador,
            velocidade_evaporador,
            tempo,
        )

        self.succao.valor = aproximar(
            self.succao.valor,
            30.0,
            0.035 * fator,
            tempo,
        )

        self.descarga.valor = aproximar(
            self.descarga.valor,
            218.0 + 12.0 * intensidade,
            0.032 * fator,
            tempo,
        )

        self.temperatura_descarga.valor = aproximar(
            self.temperatura_descarga.valor,
            82.0 + 10.0 * intensidade,
            0.035 * fator,
            tempo,
        )

        self.temperatura_succao.valor = aproximar(
            self.temperatura_succao.valor,
            self.evaporador.valor + 3.0,
            0.045 * fator,
            tempo,
        )

        self.temperatura_liquido.valor = aproximar(
            self.temperatura_liquido.valor,
            36.0,
            0.030 * fator,
            tempo,
        )

        self._aplicar_ruido_suave(0.35)

    def _atualizar_falha(self, tempo: float, fator: float) -> None:
        self._restaurar_valores_normais()
        self._atualizar_parada(tempo, fator)
        self._salvar_valores_normais()
        falhas = {
            1: lambda: setattr(self.camara, "valor", self.camara.maximo),
            2: lambda: setattr(self.evaporador, "valor", self.evaporador.minimo),
            3: lambda: setattr(self.succao, "valor", self.succao.maximo),
            4: lambda: setattr(self.descarga, "valor", self.descarga.minimo),
            5: lambda: setattr(self.temperatura_descarga, "valor", 130.0),
            6: lambda: setattr(self.descarga, "valor", 450.0),
            7: lambda: setattr(self.succao, "valor", 5.0),
            8: lambda: setattr(self.descarga, "valor", 450.0),
            9: lambda: setattr(self.succao, "valor", 5.0),
            10: lambda: None,
        }
        falhas[self.numero_falha]()

    def _avaliar_alarmes_automaticos(
        self,
        canais_validos: set[str] | None = None,
        avaliar_limites_sensor: bool = True,
    ) -> None:
        def disponivel(nome: str) -> bool:
            return canais_validos is None or nome in canais_validos

        self.alarme_temp_camara = (
            self._avaliar_histerese_alta(self.alarme_temp_camara, self.camara.valor, TEMP_CAMARA_ALTA_ON, TEMP_CAMARA_ALTA_OFF)
            if disponivel("temperatura_camara") else False
        )
        self.alarme_descarga = (
            self._avaliar_histerese_alta(self.alarme_descarga, self.descarga.valor, PRESSAO_DESCARGA_ALTA_ON, PRESSAO_DESCARGA_ALTA_OFF)
            if disponivel("pressao_descarga_psi") else False
        )
        self.alarme_succao = (
            self._avaliar_histerese_baixa(self.alarme_succao, self.succao.valor, PRESSAO_SUCCAO_BAIXA_ON, PRESSAO_SUCCAO_BAIXA_OFF)
            if disponivel("pressao_succao_psi") else False
        )
        self.alarme_temp_descarga = (
            self._avaliar_histerese_alta(self.alarme_temp_descarga, self.temperatura_descarga.valor, TEMP_DESCARGA_ALTA_ON, TEMP_DESCARGA_ALTA_OFF)
            if disponivel("temperatura_descarga") else False
        )

        alarmes: list[str] = []
        if self.alarme_temp_camara:
            alarmes.append("ALTA TEMPERATURA DA CÂMARA")
        if self.alarme_descarga:
            alarmes.append("ALTA PRESSÃO DE DESCARGA")
        if self.alarme_succao:
            alarmes.append("BAIXA PRESSÃO DE SUCÇÃO")
        if self.alarme_temp_descarga:
            alarmes.append("ALTA TEMPERATURA DE DESCARGA")
        if (
            avaliar_limites_sensor
            and disponivel("temperatura_camara")
            and self.camara.valor >= self.camara.maximo
        ):
            alarmes.append("FALHA DO SENSOR DA CÂMARA")
        if (
            avaliar_limites_sensor
            and disponivel("temperatura_evaporador")
            and self.evaporador.valor <= self.evaporador.minimo
        ):
            alarmes.append("FALHA DO SENSOR DO EVAPORADOR")
        self.alarmes_automaticos = alarmes
        self.em_alarme_automatico = bool(alarmes)

    @staticmethod
    def _avaliar_histerese_alta(ativo: bool, valor: float, limite_on: float, limite_off: float) -> bool:
        return valor >= limite_on if not ativo else valor > limite_off

    @staticmethod
    def _avaliar_histerese_baixa(ativo: bool, valor: float, limite_on: float, limite_off: float) -> bool:
        return valor <= limite_on if not ativo else valor < limite_off

    def _aplicar_ruido(self) -> None:
        """Compatibilidade com chamadas antigas."""
        self._aplicar_ruido_suave(1.0)

    def _aplicar_ruido_suave(self, escala: float = 1.0) -> None:
        intensidade = self.agressividade / 100.0
        ganho = intensidade * escala

        self.camara.valor += random.uniform(-0.015, 0.015) * ganho
        self.evaporador.valor += random.uniform(-0.05, 0.05) * ganho
        self.succao.valor += random.uniform(-0.35, 0.35) * ganho
        self.descarga.valor += random.uniform(-1.2, 1.2) * ganho
        self.temperatura_descarga.valor += random.uniform(-0.12, 0.12) * ganho
        self.temperatura_succao.valor += random.uniform(-0.05, 0.05) * ganho
        self.temperatura_liquido.valor += random.uniform(-0.05, 0.05) * ganho

    def _aplicar_picos(self) -> None:
        """Compatibilidade com chamadas antigas."""
        self._aplicar_picos_suaves()

    def _aplicar_picos_suaves(self) -> None:
        intensidade = self.agressividade / 100.0
        probabilidade = 0.002 + 0.008 * intensidade

        if random.random() < probabilidade:
            self.succao.valor += random.uniform(-2.0, 2.0) * intensidade

        if random.random() < probabilidade:
            self.descarga.valor += random.uniform(-6.0, 8.0) * intensidade

    def _aplicar_limites(self) -> None:
        for canal in self.canais:
            canal.valor = limitar(canal.valor, canal.minimo, canal.maximo)


class Historico:
    def __init__(self) -> None:
        self.caminho = Path(ARQUIVO_HISTORICO)
        if not self.caminho.exists():
            self._criar_arquivo()

    def _criar_arquivo(self) -> None:
        cabecalho = ["Data", "Hora", "Modo", "Falha", "Agressividade (%)"]
        cabecalho.extend(f"CH{canal.numero} {canal.nome} ({canal.unidade})" for canal in CANAIS)
        cabecalho.extend(["Refrigerante", "Superaquecimento (°C)", "Sub-resfriamento (°C)"])
        with self.caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
            csv.writer(arquivo, delimiter=";").writerow(cabecalho)

    def salvar(self, gerador: GeradorRefrigeracao) -> None:
        agora = datetime.now()
        linha = [
            agora.strftime("%d/%m/%Y"),
            agora.strftime("%H:%M:%S"),
            gerador.nome_modo,
            gerador.nome_falha if gerador.modo == 4 else gerador.nome_alarme_automatico,
            gerador.agressividade,
            *[self._formatar(canal.valor) for canal in gerador.canais],
            gerador.refrigerante,
            self._formatar_opcional(gerador.superaquecimento),
            self._formatar_opcional(gerador.subresfriamento),
        ]
        with self.caminho.open("a", newline="", encoding="utf-8-sig") as arquivo:
            csv.writer(arquivo, delimiter=";").writerow(linha)

    @staticmethod
    def _formatar(valor: float) -> str:
        return f"{valor:.2f}".replace(".", ",")

    @classmethod
    def _formatar_opcional(cls, valor: float | None) -> str:
        return "" if valor is None else cls._formatar(valor)
