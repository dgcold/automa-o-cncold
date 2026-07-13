# -*- coding: utf-8 -*-

from controllers.condensacao import CondensacaoController


class Condensador:
    def __init__(self):
        self.ventilador_1 = False
        self.ventilador_2 = False
        self.controle = CondensacaoController()

    def controlar(self, compressor_ligado, pressao_descarga):
        if not compressor_ligado:
            self.ventilador_1 = False
            self.ventilador_2 = False
            self.controle.resetar()

            print("DO_VentiladorCondensador_1 = OFF")
            print("DO_VentiladorCondensador_2 = OFF")
            return

        self.ventilador_1 = True

        self.ventilador_2 = self.controle.segundo_ventilador(
            pressao_descarga
        )

        print("DO_VentiladorCondensador_1 = ON")
        print(
            "DO_VentiladorCondensador_2 = "
            f"{'ON' if self.ventilador_2 else 'OFF'}"
        )