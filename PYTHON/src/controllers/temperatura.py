# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : temperatura.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Controlador de temperatura da camara frigorifica.
#
# Responsavel por:
#
# • Comparar a temperatura da camara com o setpoint.
# • Aplicar o diferencial (histerese).
# • Informar quando iniciar ou parar a refrigeracao.
# ==============================================================

from config.machine_config import MachineConfig


class TemperaturaController:
    """
    Controlador de temperatura da camara.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Carrega os parametros de temperatura.
        """

        self.setpoint = MachineConfig.SETPOINT
        self.diferencial = MachineConfig.DIFERENCIAL

    # ==========================================================
    # PEDIDO DE REFRIGERACAO
    # ==========================================================

    def precisa_refrigerar(self, temperatura_atual):
        """
        Verifica se existe necessidade de refrigeracao.

        A refrigeracao inicia quando:

            Temperatura >
            Setpoint + Diferencial
        """

        return (
            temperatura_atual >
            self.setpoint + self.diferencial
        )

    # ==========================================================
    # SETPOINT ATINGIDO
    # ==========================================================

    def atingiu_setpoint(self, temperatura_atual):
        """
        Verifica se a temperatura chegou ao setpoint.

        Retorna:

            True
                Temperatura atingida.

            False
                Continuar refrigerando.
        """

        return temperatura_atual <= self.setpoint

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna os parametros atuais do controlador.
        """

        return {
            "setpoint": self.setpoint,
            "diferencial": self.diferencial,
        }