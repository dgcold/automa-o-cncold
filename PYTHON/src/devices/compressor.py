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
# Responsavel pelo controle do compressor da maquina frigorifica.
#
# Funcoes:
#
#   - Ligar o compressor
#   - Desligar o compressor
#   - Controlar o tempo de anti-rearme
#   - Informar o estado atual do compressor
#
# O anti-rearme impede uma nova partida logo apos o desligamento,
# protegendo o compressor contra partidas consecutivas.
# ==============================================================

from config.machine_config import MachineConfig
from core.timer import Timer


class Compressor:
    """
    Controle da saida digital do compressor.
    """

    def __init__(self):
        """
        Inicializa o compressor desligado e inicia o temporizador
        de anti-rearme.
        """

        self.ligado = False

        self.timer_antirearme = Timer()
        self.timer_antirearme.iniciar()

    def pode_ligar(self):
        """
        Verifica se o tempo de anti-rearme foi cumprido.

        Retorna:
            True  - compressor liberado para partir.
            False - compressor bloqueado pelo anti-rearme.
        """

        if self.ligado:
            return True

        return self.timer_antirearme.expirou(
            MachineConfig.ANTI_REARME_SEGUNDOS
        )

    def ligar(self):
        """
        Liga o compressor quando o anti-rearme estiver liberado.

        Retorna:
            True  - compressor ligado ou ja estava ligado.
            False - partida bloqueada pelo anti-rearme.
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

    def desligar(self):
        """
        Desliga o compressor.

        Quando ocorre o desligamento, o temporizador de
        anti-rearme e reiniciado.
        """

        if not self.ligado:
            return False

        self.ligado = False

        self.timer_antirearme.reiniciar()

        print("DO_Compressor = OFF")

        return True

    def esta_ligado(self):
        """
        Retorna o estado atual do compressor.
        """

        return self.ligado

    def status(self):
        """
        Retorna as informacoes do compressor.
        """

        return {
            "ligado": self.ligado,
            "anti_rearme_liberado": self.pode_ligar(),
            "tempo_anti_rearme": (
                MachineConfig.ANTI_REARME_SEGUNDOS
            ),
        }