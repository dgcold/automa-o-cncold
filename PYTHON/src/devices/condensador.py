# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : condensador.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.1
#
# DESCRICAO
# --------------------------------------------------------------
# Controle dos ventiladores do condensador.
#
# FAN 1
#   - Liga junto com o compressor.
#   - Desliga quando o compressor desliga.
#
# FAN 2
#   - Controlado pela pressao de descarga.
#   - Utiliza histerese para evitar chaveamentos.
#
# Esta estrutura sera utilizada futuramente no ISaGRAF.
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
        Atualiza o estado dos ventiladores.
        """

        fan1_anterior = self.ventilador_1
        fan2_anterior = self.ventilador_2

        # Compressor desligado
        if not compressor_ligado:

            self.ventilador_1 = False
            self.ventilador_2 = False

            self.controle.resetar()

        # Compressor ligado
        else:

            # Fan 1 permanece ligado enquanto houver refrigeracao
            self.ventilador_1 = True

            # Fan 2 depende da pressao de descarga
            self.ventilador_2 = (
                self.controle.segundo_ventilador(
                    pressao_descarga
                )
            )

        # Atualiza somente quando houver mudanca
        if fan1_anterior != self.ventilador_1:

            print(
                "DO_VentiladorCondensador_1 = "
                f"{'ON' if self.ventilador_1 else 'OFF'}"
            )

        if fan2_anterior != self.ventilador_2:

            print(
                "DO_VentiladorCondensador_2 = "
                f"{'ON' if self.ventilador_2 else 'OFF'}"
            )

    def desligar(self):
        """
        Desliga completamente o condensador.
        """

        self.controlar(False, 0.0)

    def fan1_ligado(self):
        """
        Retorna o estado do ventilador 1.
        """

        return self.ventilador_1

    def fan2_ligado(self):
        """
        Retorna o estado do ventilador 2.
        """

        return self.ventilador_2

    def status(self):
        """
        Retorna o estado dos ventiladores.
        """

        return {
            "ventilador_1": self.ventilador_1,
            "ventilador_2": self.ventilador_2,
        }