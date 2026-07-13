# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : oleo.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pela protecao de pressao de oleo do compressor.
#
# Funcao:
#
# • Monitorar o pressostato de oleo.
# • Temporizar a falha.
# • Evitar desligamentos por pulsos momentaneos.
#
# O alarme somente e gerado quando o pressostato permanecer
# acionado durante todo o tempo configurado.
# ==============================================================

from config.machine_config import MachineConfig
from core.timer import Timer


class OleoController:
    """
    Controlador da protecao de oleo.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o temporizador da protecao de oleo.
        """

        self.timer = Timer()

    # ==========================================================
    # VERIFICACAO DA PRESSAO DE OLEO
    # ==========================================================

    def verificar(
        self,
        compressor_ligado,
        pressostato_oleo_atuado
    ):
        """
        Verifica a pressao de oleo.

        Regras:

            Compressor desligado

                • Protecao desabilitada.

            Pressostato normal

                • Temporizador parado.

            Pressostato atuado

                • Inicia temporizacao.

            Tempo excedido

                • Retorna falha.
        """

        # ------------------------------------------------------
        # COMPRESSOR DESLIGADO
        # ------------------------------------------------------

        if not compressor_ligado:

            self.timer.parar()

            return True

        # ------------------------------------------------------
        # PRESSAO NORMAL
        # ------------------------------------------------------

        if not pressostato_oleo_atuado:

            self.timer.parar()

            return True

        # ------------------------------------------------------
        # INICIA TEMPORIZACAO
        # ------------------------------------------------------

        if self.timer.inicio is None:

            print(
                "Monitorando pressao de oleo..."
            )

            self.timer.iniciar()

        # ------------------------------------------------------
        # TEMPO MAXIMO
        # ------------------------------------------------------

        if self.timer.expirou(
            MachineConfig.TEMPO_MAXIMO_OLEO_SEGUNDOS
        ):

            print(
                "Falha de pressao de oleo."
            )

            return False

        return True

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado do temporizador da protecao.
        """

        return self.timer.inicio is not None