# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : solenoide_gas_quente.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo acionamento da valvula solenoide de gas
# quente utilizada durante o ciclo de degelo.
#
# Funcao:
#
# • Liberar gas quente para o evaporador.
# • Permanecer desligada durante a refrigeracao.
# • Fechar imediatamente ao finalizar o degelo.
# ==============================================================


class SolenoideGasQuente:
    """
    Controle da valvula solenoide de gas quente.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa a solenoide de gas quente.
        """

        self.ligada = False

    # ==========================================================
    # LIGAR
    # ==========================================================

    def ligar(self):
        """
        Liga a valvula de gas quente.

        Utilizada exclusivamente durante o ciclo de degelo.
        """

        if self.ligada:
            return

        self.ligada = True

        print("DO_GasQuente = ON")

    # ==========================================================
    # DESLIGAR
    # ==========================================================

    def desligar(self):
        """
        Desliga a valvula de gas quente.
        """

        if not self.ligada:
            return

        self.ligada = False

        print("DO_GasQuente = OFF")

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual da solenoide.

        True  -> Ligada

        False -> Desligada
        """

        return self.ligada