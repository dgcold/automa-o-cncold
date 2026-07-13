# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : condensacao.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle do segundo ventilador do condensador.
#
# Funcao:
#
# • Monitorar a pressao de descarga.
# • Acionar o Fan 2 quando a pressao ultrapassar o limite.
# • Desligar o Fan 2 utilizando histerese.
#
# O objetivo e manter a condensacao dentro da faixa desejada,
# evitando acionamentos excessivos do ventilador.
# ==============================================================

from config.machine_config import MachineConfig


class CondensacaoController:
    """
    Controlador do segundo ventilador do condensador.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self, fan2_on=None, fan2_off=None):
        """
        Inicializa os limites de acionamento do Fan 2.

        Caso nenhum valor seja informado, utiliza os parametros
        definidos em MachineConfig.
        """

        self.fan2_on = (
            MachineConfig.FAN2_ON_PSI
            if fan2_on is None
            else fan2_on
        )

        self.fan2_off = (
            MachineConfig.FAN2_OFF_PSI
            if fan2_off is None
            else fan2_off
        )

        self.fan2_ligado = False

    # ==========================================================
    # CONTROLE DO FAN 2
    # ==========================================================

    def segundo_ventilador(self, pressao):
        """
        Controla o segundo ventilador utilizando histerese.

        Regras:

            Pressao >= FAN2_ON
                Liga o Fan 2.

            Pressao <= FAN2_OFF
                Desliga o Fan 2.

        Retorno:

            True
                Fan 2 ligado.

            False
                Fan 2 desligado.
        """

        # Liga o Fan 2.

        if (
            not self.fan2_ligado
            and pressao >= self.fan2_on
        ):

            self.fan2_ligado = True

            print(
                "Fan 2 ligado por alta pressao."
            )

        # Desliga o Fan 2.

        elif (
            self.fan2_ligado
            and pressao <= self.fan2_off
        ):

            self.fan2_ligado = False

            print(
                "Fan 2 desligado por reducao da pressao."
            )

        return self.fan2_ligado

    # ==========================================================
    # RESET
    # ==========================================================

    def resetar(self):
        """
        Reinicia o estado do controlador.

        Utilizado quando o compressor desliga.
        """

        self.fan2_ligado = False

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual do controlador.
        """

        return {
            "fan2_ligado": self.fan2_ligado,
            "fan2_on": self.fan2_on,
            "fan2_off": self.fan2_off,
        }