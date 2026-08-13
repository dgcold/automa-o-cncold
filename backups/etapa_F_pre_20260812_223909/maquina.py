import random

import configuracao as cfg


class MaquinaSimulada:
    def __init__(self):
        # Valores internos reais do processo
        self._temperatura_camara = cfg.TEMP_CAMARA_INICIAL
        self._temperatura_evaporador = cfg.TEMP_EVAPORADOR_INICIAL

        self._pressao_succao = cfg.PRESSAO_SUCCAO_INICIAL
        self._pressao_descarga = cfg.PRESSAO_DESCARGA_INICIAL
        self._pressao_oleo = cfg.PRESSAO_OLEO_INICIAL

        # Valores apresentados como sensores
        self.temperatura_camara = self._temperatura_camara
        self.temperatura_evaporador = self._temperatura_evaporador

        self.pressao_succao = self._pressao_succao
        self.pressao_descarga = self._pressao_descarga
        self.pressao_oleo = self._pressao_oleo

        # Estados da máquina
        self.compressor_ligado = False
        self.degelo_ligado = False
        self.modo_automatico = cfg.MODO_AUTOMATICO
        self.agressividade = cfg.AGRESSIVIDADE_INICIAL

    def ligar_compressor(self):
        if not self.degelo_ligado:
            self.compressor_ligado = True

    def desligar_compressor(self):
        self.compressor_ligado = False

    def alternar_degelo(self):
        self.degelo_ligado = not self.degelo_ligado

        if self.degelo_ligado:
            self.compressor_ligado = False

    def aumentar_agressividade(self):
        self.agressividade = min(
            cfg.AGRESSIVIDADE_MAX,
            self.agressividade + cfg.PASSO_AGRESSIVIDADE,
        )

    def diminuir_agressividade(self):
        self.agressividade = max(
            cfg.AGRESSIVIDADE_MIN,
            self.agressividade - cfg.PASSO_AGRESSIVIDADE,
        )

    def controlar_temperatura(self):
        if not self.modo_automatico:
            return

        if self.degelo_ligado:
            self.compressor_ligado = False
            return

        temperatura_desligamento = cfg.SETPOINT_CAMARA

        temperatura_religamento = (
            cfg.SETPOINT_CAMARA
            + cfg.DIFERENCIAL_CAMARA
        )

        if (
            self.compressor_ligado
            and self._temperatura_camara
            <= temperatura_desligamento
        ):
            self.compressor_ligado = False

        elif (
            not self.compressor_ligado
            and self._temperatura_camara
            >= temperatura_religamento
        ):
            self.compressor_ligado = True

    def atualizar(self, tempo_decorrido):
        self.controlar_temperatura()

        fator = 1.0 + self.agressividade / 100.0

        if self.degelo_ligado:
            self._atualizar_degelo(
                tempo_decorrido,
                fator,
            )

        elif self.compressor_ligado:
            self._atualizar_resfriamento(
                tempo_decorrido,
                fator,
            )

        else:
            self._atualizar_parada(
                tempo_decorrido,
                fator,
            )

        self._aplicar_limites()
        self._atualizar_sensores()

    def _atualizar_resfriamento(
        self,
        tempo_decorrido,
        fator,
    ):
        queda_por_segundo = (
            cfg.QUEDA_CAMARA_GRAUS
            / cfg.QUEDA_CAMARA_SEGUNDOS
        )

        self._temperatura_camara -= (
            queda_por_segundo
            * tempo_decorrido
            * fator
        )

        alvo_evaporador = (
            self._temperatura_camara
            - cfg.TEMP_DIFERENCA_EVAPORADOR
        )

        self._temperatura_evaporador += (
            alvo_evaporador
            - self._temperatura_evaporador
        ) * 0.05 * tempo_decorrido * fator

        alvo_succao = (
            cfg.PRESSAO_SUCCAO_ALVO
            - self.agressividade * 0.03
        )

        alvo_descarga = (
            cfg.PRESSAO_DESCARGA_ALVO
            + self.agressividade * 0.25
        )

        alvo_oleo = (
            alvo_succao
            + cfg.DIFERENCIAL_OLEO_ALVO
        )

        self._pressao_succao += (
            alvo_succao
            - self._pressao_succao
        ) * 0.04 * tempo_decorrido * fator

        self._pressao_descarga += (
            alvo_descarga
            - self._pressao_descarga
        ) * 0.04 * tempo_decorrido * fator

        self._pressao_oleo += (
            alvo_oleo
            - self._pressao_oleo
        ) * 0.04 * tempo_decorrido * fator

    def _atualizar_parada(
        self,
        tempo_decorrido,
        fator,
    ):
        subida_por_segundo = (
            cfg.SUBIDA_CAMARA_GRAUS
            / cfg.SUBIDA_CAMARA_SEGUNDOS
        )

        self._temperatura_camara += (
            subida_por_segundo
            * tempo_decorrido
            * fator
        )

        self._temperatura_evaporador += (
            self._temperatura_camara
            - self._temperatura_evaporador
        ) * 0.03 * tempo_decorrido

        self._pressao_succao += (
            cfg.PRESSAO_EQUALIZACAO
            - self._pressao_succao
        ) * 0.02 * tempo_decorrido

        self._pressao_descarga += (
            cfg.PRESSAO_EQUALIZACAO
            - self._pressao_descarga
        ) * 0.02 * tempo_decorrido

        self._pressao_oleo += (
            self._pressao_succao
            - self._pressao_oleo
        ) * 0.03 * tempo_decorrido

    def _atualizar_degelo(
        self,
        tempo_decorrido,
        fator,
    ):
        self._temperatura_camara += (
            cfg.SUBIDA_CAMARA_DEGELO_POR_SEGUNDO
            * tempo_decorrido
            * fator
        )

        self._temperatura_evaporador += (
            cfg.SUBIDA_EVAPORADOR_DEGELO_POR_SEGUNDO
            * tempo_decorrido
            * fator
        )

        self._pressao_succao += (
            cfg.PRESSAO_SUCCAO_DEGELO_ALVO
            - self._pressao_succao
        ) * 0.03 * tempo_decorrido

        self._pressao_descarga += (
            cfg.PRESSAO_DESCARGA_DEGELO_ALVO
            - self._pressao_descarga
        ) * 0.03 * tempo_decorrido

        self._pressao_oleo += (
            self._pressao_succao
            - self._pressao_oleo
        ) * 0.03 * tempo_decorrido

    def _atualizar_sensores(self):
        intensidade = self.agressividade / 100.0

        ruido_temp_camara = random.uniform(
            -0.05,
            0.05,
        ) * intensidade

        ruido_temp_evaporador = random.uniform(
            -0.08,
            0.08,
        ) * intensidade

        ruido_succao = random.uniform(
            -1.0,
            1.0,
        ) * intensidade

        ruido_descarga = random.uniform(
            -2.5,
            2.5,
        ) * intensidade

        ruido_oleo = random.uniform(
            -1.0,
            1.0,
        ) * intensidade

        self.temperatura_camara = (
            self._temperatura_camara
            + ruido_temp_camara
        )

        self.temperatura_evaporador = (
            self._temperatura_evaporador
            + ruido_temp_evaporador
        )

        self.pressao_succao = (
            self._pressao_succao
            + ruido_succao
        )

        self.pressao_descarga = (
            self._pressao_descarga
            + ruido_descarga
        )

        self.pressao_oleo = (
            self._pressao_oleo
            + ruido_oleo
        )

        self._aplicar_picos_aleatorios()

    def _aplicar_picos_aleatorios(self):
        intensidade = self.agressividade / 100.0

        probabilidade = 0.003 + (
            0.02 * intensidade
        )

        if random.random() < probabilidade:
            self.pressao_succao += random.uniform(
                -8.0,
                8.0,
            ) * intensidade

        if random.random() < probabilidade:
            self.pressao_descarga += random.uniform(
                -20.0,
                25.0,
            ) * intensidade

        if random.random() < probabilidade:
            self.temperatura_evaporador += random.uniform(
                -1.0,
                1.0,
            ) * intensidade

    def _aplicar_limites(self):
        self._temperatura_camara = max(
            cfg.TEMP_CAMARA_MIN,
            min(
                cfg.TEMP_CAMARA_MAX,
                self._temperatura_camara,
            ),
        )

        self._temperatura_evaporador = max(
            cfg.TEMP_EVAPORADOR_MIN,
            min(
                cfg.TEMP_EVAPORADOR_MAX,
                self._temperatura_evaporador,
            ),
        )

        self._pressao_succao = max(
            cfg.PRESSAO_SUCCAO_MIN,
            min(
                cfg.PRESSAO_SUCCAO_MAX,
                self._pressao_succao,
            ),
        )

        self._pressao_descarga = max(
            cfg.PRESSAO_DESCARGA_MIN,
            min(
                cfg.PRESSAO_DESCARGA_MAX,
                self._pressao_descarga,
            ),
        )

        self._pressao_oleo = max(
            cfg.PRESSAO_OLEO_MIN,
            min(
                cfg.PRESSAO_OLEO_MAX,
                self._pressao_oleo,
            ),
        )