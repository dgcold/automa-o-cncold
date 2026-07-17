# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : degelo.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.1
#
# DESCRICAO
# --------------------------------------------------------------
# Controle do ciclo de degelo por gas quente.
#
# Funcoes:
#
#   - Iniciar o degelo
#   - Finalizar o degelo
#   - Verificar temperatura de termino
#   - Informar o estado atual
#
# O tempo maximo do degelo e controlado pela Machine.
# Esta classe controla apenas o estado do degelo.
# ==============================================================

from config.machine_config import MachineConfig


class Degelo:
    """
    Controle do ciclo de degelo.
    """

    def __init__(self):
        """
        Inicializa o controlador.
        """

        self.ativo = False

        self.temperatura_fim = (
            MachineConfig.TEMPERATURA_FIM_DEGELO
        )

    def iniciar(self):
        """
        Inicia o ciclo de degelo.
        """

        if self.ativo:
            return

        self.ativo = True

        print("DO_Degelo = ON")

    def finalizar(self):
        """
        Finaliza o ciclo de degelo.
        """

        if not self.ativo:
            return

        self.ativo = False

        print("DO_Degelo = OFF")

    def deve_finalizar(
        self,
        temperatura_evaporador
    ):
        """
        Verifica se a temperatura de termino
        do degelo foi atingida.

        Retorna:
            True  -> Finalizar degelo.
            False -> Continuar degelo.
        """

        return (
            temperatura_evaporador
            >= self.temperatura_fim
        )

    def em_degelo(self):
        """
        Retorna True quando o degelo estiver ativo.
        """

        return self.ativo

    def status(self):
        """
        Retorna o estado atual do degelo.
        """

        return {
            "ativo": self.ativo,
            "temperatura_final": self.temperatura_fim,
        }