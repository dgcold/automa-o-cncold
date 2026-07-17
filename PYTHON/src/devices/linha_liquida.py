# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : linha_liquida.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.1
#
# DESCRICAO
# --------------------------------------------------------------
# Controle da valvula solenoide da linha de liquido.
#
# Funcao:
#
#   - Liberar refrigerante para o evaporador.
#   - Interromper o fluxo durante a parada.
#   - Auxiliar na sequencia de refrigeracao.
#
# Sequencia correta:
#
#   1 - Abrir linha de liquido.
#   2 - Ligar compressor.
#
# Parada:
#
#   1 - Fechar linha de liquido.
#   2 - Desligar compressor.
#
# Estrutura preparada para migracao ao ISaGRAF.
# ==============================================================


class LinhaLiquida:
    """
    Controle da valvula solenoide da linha de liquido.
    """

    def __init__(self):
        """
        Inicializa a valvula fechada.
        """

        self.ligada = False

    def ligar(self):
        """
        Abre a valvula da linha de liquido.
        """

        if self.ligada:
            return True

        self.ligada = True

        print("DO_LinhaLiquida = ON")

        return True

    def desligar(self):
        """
        Fecha a valvula da linha de liquido.
        """

        if not self.ligada:
            return False

        self.ligada = False

        print("DO_LinhaLiquida = OFF")

        return True

    def esta_ligada(self):
        """
        Retorna o estado atual da valvula.
        """

        return self.ligada

    def status(self):
        """
        Retorna as informacoes da linha de liquido.
        """

        return {
            "ligada": self.ligada
        }