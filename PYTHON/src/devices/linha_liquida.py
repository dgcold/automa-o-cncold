# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : linha_liquida.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle da solenoide da linha de liquido.
#
# Funcao:
#
# • Liberar refrigerante para o evaporador.
# • Interromper o fluxo durante a parada.
# • Auxiliar na sequencia de refrigeracao.
#
# A linha de liquido sempre deve ser aberta antes da partida
# do compressor e fechada antes do desligamento.
# ==============================================================


class LinhaLiquida:
    """
    Controle da valvula solenoide da linha de liquido.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa a linha de liquido.
        """

        self.ligada = False

    # ==========================================================
    # LIGAR
    # ==========================================================

    def ligar(self):
        """
        Liga a linha de liquido.

        Permite a passagem do refrigerante para o evaporador.
        """

        if self.ligada:
            return

        self.ligada = True

        print("DO_LinhaLiquida = ON")

    # ==========================================================
    # DESLIGAR
    # ==========================================================

    def desligar(self):
        """
        Desliga a linha de liquido.

        Interrompe o fluxo de refrigerante.
        """

        if not self.ligada:
            return

        self.ligada = False

        print("DO_LinhaLiquida = OFF")

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual da linha de liquido.

        True  -> Ligada

        False -> Desligada
        """

        return self.ligada