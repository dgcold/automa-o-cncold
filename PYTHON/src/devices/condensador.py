# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : condensador.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Controla os dois ventiladores do condensador.
#
# Fan 1:
#   Ligado enquanto o compressor estiver ligado.
#
# Fan 2:
#   Controlado pela pressao de descarga com histerese.
#
# As mensagens sao exibidas somente quando ocorre mudanca
# real nas saidas.
# ==============================================================

from controllers.condensacao import CondensacaoController


class Condensador:
    """
    Controle dos ventiladores do condensador.
    """

    def __init__(self):
        self.ventilador_1 = False
        self.ventilador_2 = False

        self.controle = CondensacaoController()

    def controlar(
        self,
        compressor_ligado,
        pressao_descarga
    ):
        """
        Atualiza os ventiladores conforme o compressor
        e a pressao de descarga.
        """

        estado_anterior_fan1 = self.ventilador_1
        estado_anterior_fan2 = self.ventilador_2

        if not compressor_ligado:
            self.ventilador_1 = False
            self.ventilador_2 = False

            self.controle.resetar()

        else:
            self.ventilador_1 = True

            self.ventilador_2 = (
                self.controle.segundo_ventilador(
                    pressao_descarga
                )
            )

        if estado_anterior_fan1 != self.ventilador_1:
            print(
                "DO_VentiladorCondensador_1 = "
                f"{'ON' if self.ventilador_1 else 'OFF'}"
            )

        if estado_anterior_fan2 != self.ventilador_2:
            print(
                "DO_VentiladorCondensador_2 = "
                f"{'ON' if self.ventilador_2 else 'OFF'}"
            )

    def status(self):
        """
        Retorna o estado atual dos ventiladores.
        """

        return {
            "Fan1": self.ventilador_1,
            "Fan2": self.ventilador_2,
        }