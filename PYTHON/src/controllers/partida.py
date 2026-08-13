# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : partida.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Autoriza ou bloqueia o funcionamento da maquina conforme
# a existencia de alarmes ativos.
# ==============================================================


class PartidaController:
    """
    Controlador da permissao de funcionamento.
    """

    def __init__(self):
        self.habilitado = True

    def liberar(self, alarmes):
        """
        Libera a maquina somente quando nao existem alarmes.
        """

        self.habilitado = len(alarmes) == 0

        return self.habilitado

    def status(self):
        """
        Retorna o estado da permissao.
        """

        return self.habilitado