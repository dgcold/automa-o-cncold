# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : degelo.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle do ciclo de degelo por gas quente.
#
# Recursos:
#
# • Iniciar degelo
# • Finalizar degelo
# • Monitorar temperatura do evaporador
# • Informar estado atual
#
# O degelo e encerrado quando a temperatura configurada
# do evaporador for atingida ou pelo tempo maximo
# definido na maquina principal.
# ==============================================================

from config.machine_config import MachineConfig


class Degelo:
    """
    Controle do ciclo de degelo.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o controlador de degelo.
        """

        self.ativo = False

        self.temperatura_fim = (
            MachineConfig.TEMPERATURA_FIM_DEGELO
        )

    # ==========================================================
    # INICIAR DEGELO
    # ==========================================================

    def iniciar(self):
        """
        Ativa o ciclo de degelo.
        """

        self.ativo = True

        print("DO_Degelo = ON")

    # ==========================================================
    # FINALIZAR DEGELO
    # ==========================================================

    def finalizar(self):
        """
        Finaliza o ciclo de degelo.
        """

        self.ativo = False

        print("DO_Degelo = OFF")

    # ==========================================================
    # VERIFICAR FINAL DO DEGELO
    # ==========================================================

    def deve_finalizar(
        self,
        temperatura_evaporador
    ):
        """
        Verifica se a temperatura final do evaporador
        foi atingida.

        Retorno:

            True
                Degelo concluido.

            False
                Continuar degelo.
        """

        return (
            temperatura_evaporador
            >= self.temperatura_fim
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual do degelo.
        """

        return self.ativo