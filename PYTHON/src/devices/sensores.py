class Sensores:

    def __init__(self):

        self.temp_camara = -15.0
        self.temp_evaporador = -22.0

        self.pressao_succao = 28.0
        self.pressao_descarga = 260.0
        self.pressao_oleo = 45.0

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