# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : compressor.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle do compressor da camara frigorifica.
#
# Recursos:
#
#   • Liga o compressor
#   • Desliga o compressor
#   • Controle de anti-rearme
#   • Informa o estado atual
#
# O anti-rearme protege o compressor contra partidas
# consecutivas em um intervalo muito pequeno.
# ==============================================================

from config.machine_config import MachineConfig
from core.timer import Timer


class Compressor:
    """
    Classe responsavel pelo controle do compressor.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o compressor.

        O temporizador de anti-rearme e iniciado para impedir
        partidas consecutivas logo apos o desligamento.
        """

        self.ligado = False

        self.timer_antirearme = Timer()
        self.timer_antirearme.iniciar()

    # ==========================================================
    # VERIFICACAO DO ANTI-REARME
    # ==========================================================

    def pode_ligar(self):
        """
        Verifica se o tempo de anti-rearme foi cumprido.

        Retorno:

            True
                Compressor liberado.

            False
                Compressor ainda bloqueado pelo temporizador.
        """

        return self.timer_antirearme.expirou(
            MachineConfig.ANTI_REARME_SEGUNDOS
        )

    # ==========================================================
    # LIGA COMPRESSOR
    # ==========================================================

    def ligar(self):
        """
        Liga o compressor.

        Sequencia:

            1. Verifica se ja esta ligado.
            2. Verifica o anti-rearme.
            3. Aciona a saida do compressor.

        Retorno:

            True
                Compressor ligado.

            False
                Compressor bloqueado.
        """

        if self.ligado:
            return True

        if not self.pode_ligar():
            print(
                "Compressor bloqueado pelo anti-rearme."
            )
            return False

        self.ligado = True

        print("DO_Compressor = ON")

        return True

    # ==========================================================
    # DESLIGA COMPRESSOR
    # ==========================================================

    def desligar(self):
        """
        Desliga o compressor.

        Ao desligar, o temporizador de anti-rearme e reiniciado,
        impedindo uma nova partida imediata.
        """

        if not self.ligado:
            return

        self.ligado = False

        self.timer_antirearme.reiniciar()

        print("DO_Compressor = OFF")