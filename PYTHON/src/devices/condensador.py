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
# Responsavel pelo controle dos ventiladores do condensador.
#
# Recursos:
#
#   • Ventilador 1
#   • Ventilador 2
#   • Controle por pressao de descarga
#
# O ventilador 1 permanece ligado sempre que o compressor
# estiver em funcionamento.
#
# O ventilador 2 e acionado automaticamente conforme a
# pressao de descarga utilizando histerese.
# ==============================================================

from controllers.condensacao import CondensacaoController


class Condensador:
    """
    Controle dos ventiladores do condensador.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa os ventiladores e o controlador de
        condensacao.
        """

        self.ventilador_1 = False
        self.ventilador_2 = False

        self.controle = CondensacaoController()

    # ==========================================================
    # CONTROLE DOS VENTILADORES
    # ==========================================================

    def controlar(
        self,
        compressor_ligado,
        pressao_descarga
    ):
        """
        Controla os ventiladores do condensador.

        Regras:

            Compressor OFF

                • Fan 1 OFF
                • Fan 2 OFF

            Compressor ON

                • Fan 1 ON

                • Fan 2 controlado pela
                  pressao de descarga.
        """

        # ------------------------------------------------------
        # COMPRESSOR DESLIGADO
        # ------------------------------------------------------

        if not compressor_ligado:

            self.ventilador_1 = False
            self.ventilador_2 = False

            # Reinicia a histerese do controlador.
            self.controle.resetar()

            print(
                "DO_VentiladorCondensador_1 = OFF"
            )

            print(
                "DO_VentiladorCondensador_2 = OFF"
            )

            return

        # ------------------------------------------------------
        # COMPRESSOR LIGADO
        # ------------------------------------------------------

        # O ventilador principal permanece ligado durante toda
        # a refrigeracao.

        self.ventilador_1 = True

        # O segundo ventilador e acionado automaticamente pelo
        # controlador de condensacao.

        self.ventilador_2 = (
            self.controle.segundo_ventilador(
                pressao_descarga
            )
        )

        print(
            "DO_VentiladorCondensador_1 = ON"
        )

        print(
            "DO_VentiladorCondensador_2 = "
            f"{'ON' if self.ventilador_2 else 'OFF'}"
        )

    # ==========================================================
    # STATUS DOS VENTILADORES
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual dos ventiladores.

        Utilizado para futuras telas da HMI e diagnosticos.
        """

        return {
            "Fan1": self.ventilador_1,
            "Fan2": self.ventilador_2,
        }