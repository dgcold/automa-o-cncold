class Sensores:

    def __init__(self):

        # Temperaturas (°C)
        self.temp_camara = -15.0
        self.temp_evaporador = -22.0
        self.temp_ambiente = 25.0

        # Pressões (PSI)
        self.pressao_succao = 28.0
        self.pressao_descarga = 260.0
        self.pressao_oleo = 45.0

    # -------------------------
    # TEMPERATURAS
    # -------------------------

    def ler_temperatura_camara(self):
        return self.temp_camara

    def ler_temperatura_evaporador(self):
        return self.temp_evaporador

    def ler_temperatura_ambiente(self):
        return self.temp_ambiente

    # -------------------------
    # PRESSÕES
    # -------------------------

    def ler_pressao_succao(self):
        return self.pressao_succao

    def ler_pressao_descarga(self):
        return self.pressao_descarga

    def ler_pressao_oleo(self):
        return self.pressao_oleo

    # -------------------------
    # SIMULAÇÃO
    # -------------------------

    def atualizar_temperatura_camara(self, valor):
        self.temp_camara = valor

    def atualizar_pressao_descarga(self, valor):
        self.pressao_descarga = valor

    def atualizar_pressao_succao(self, valor):
        self.pressao_succao = valor

    def atualizar_pressao_oleo(self, valor):
        self.pressao_oleo = valor