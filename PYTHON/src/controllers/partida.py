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
# Responsavel por autorizar ou bloquear a partida da maquina.
#
# A partida somente sera liberada quando nao existir nenhum
# alarme ativo no sistema.
# ==============================================================


class PartidaController:
    """
    Controlador da permissao de partida.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o estado da partida.
        """

        self.habilitado = True

    # ==========================================================
    # LIBERACAO DA PARTIDA
    # ==========================================================

    def liberar(self, alarmes):
        """
        Verifica se a maquina pode iniciar a refrigeracao.

        Parametro:

            alarmes
                Lista contendo todos os alarmes ativos.

        Retorno:

            True
                Partida liberada.

            False
                Partida bloqueada.
        """

        self.habilitado = len(alarmes) == 0

        if self.habilitado:

            print("Partida liberada.")

        else:

            print("Partida bloqueada.")

            for alarme in alarmes:
                print(f"ALARME: {alarme}")

        return self.habilitado

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual da permissao de partida.

        True  -> Liberada

        False -> Bloqueada
        """

        return self.habilitado