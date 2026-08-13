# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : valvula_expansao.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle da valvula de expansao eletronica.
#
# Recursos:
#
# • Ajuste da abertura entre 0 e 100%
# • Fechamento total da valvula
# • Informacao da abertura atual
#
# Nesta versao a abertura e simulada por percentual.
# Futuramente sera substituida pelo controle do driver
# Copeland / Carel utilizando superaquecimento.
# ==============================================================


class ValvulaExpansao:
    """
    Controle da valvula de expansao eletronica.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa a valvula totalmente fechada.
        """

        self.abertura = 0

    # ==========================================================
    # POSICIONAMENTO DA VALVULA
    # ==========================================================

    def posicionar(self, percentual):
        """
        Define a abertura da valvula.

        Parametro:

            percentual

                Valor entre 0 e 100%.

        Caso o valor informado esteja fora dos limites,
        ele sera ajustado automaticamente.
        """

        percentual = max(
            0,
            min(100, int(percentual))
        )

        if self.abertura == percentual:
            return

        self.abertura = percentual

        print(
            f"AO_ValvulaExpansao = {self.abertura}%"
        )

    # ==========================================================
    # FECHAMENTO TOTAL
    # ==========================================================

    def fechar(self):
        """
        Fecha completamente a valvula.
        """

        self.posicionar(0)

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna a abertura atual da valvula.

        Retorno:

            Inteiro entre 0 e 100.
        """

        return self.abertura