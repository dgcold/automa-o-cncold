# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : evaporador.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Controla o ventilador do evaporador.
#
# O ventilador liga somente quando:
#
#   • Compressor ligado
#   • Degelo desligado
#
# A mensagem da saida somente e exibida quando ocorre
# uma mudanca real de estado.
# ==============================================================


class Evaporador:
    """
    Controle do ventilador do evaporador.
    """

    def __init__(self):
        self.ligado = False

    def controlar(
        self,
        compressor_ligado,
        degelo_ativo
    ):
        """
        Atualiza o estado do ventilador.
        """

        estado_anterior = self.ligado

        self.ligado = (
            compressor_ligado
            and not degelo_ativo
        )

        if estado_anterior != self.ligado:
            print(
                "DO_VentiladorEvaporador = "
                f"{'ON' if self.ligado else 'OFF'}"
            )

    def status(self):
        """
        Retorna o estado atual do ventilador.
        """

        return self.ligado