# -*- coding: utf-8 -*-


class Sensores:
    def __init__(self):
        self.temp_camara = -15.0
        self.temp_evaporador = -22.0
        self.pressao_succao = 28.0
        self.pressao_descarga = 260.0
        self.pressao_oleo = 45.0

    def atualizar(self, compressor_ligado):
        if compressor_ligado:
            self.temp_camara -= 0.3
            self.temp_evaporador -= 0.5
            self.pressao_succao = max(
                0.0,
                self.pressao_succao - 0.2
            )
            self.pressao_descarga += 0.5
        else:
            self.temp_camara += 0.2
            self.temp_evaporador += 0.3
            self.pressao_succao += 0.2
            self.pressao_descarga = max(
                0.0,
                self.pressao_descarga - 0.5
            )

    def exibir(self):
        print(
            f"\nCamara={self.temp_camara:.1f} C | "
            f"Evaporador={self.temp_evaporador:.1f} C | "
            f"Succao={self.pressao_succao:.1f} bar | "
            f"Descarga={self.pressao_descarga:.1f} PSI | "
            f"Oleo={self.pressao_oleo:.1f} PSI"
        )

    def ler_temperatura_camara(self):
        return self.temp_camara

    def ler_temperatura_evaporador(self):
        return self.temp_evaporador

    def ler_pressao_succao(self):
        return self.pressao_succao

    def ler_pressao_descarga(self):
        return self.pressao_descarga

    def ler_pressao_oleo(self):
        return self.pressao_oleo