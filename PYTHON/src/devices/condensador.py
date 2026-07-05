class Condensador:

    def __init__(self):
        self.ventilador_1 = False
        self.ventilador_2 = False

    def controlar(self, compressor_ligado, pressao_descarga):

        if compressor_ligado:
            self.ventilador_1 = True
        else:
            self.ventilador_1 = False
            self.ventilador_2 = False

        if pressao_descarga >= 250:
            self.ventilador_2 = True

        if pressao_descarga <= 200:
            self.ventilador_2 = False

        print(f"DO_VentiladorCondensador_1 = {'ON' if self.ventilador_1 else 'OFF'}")
        print(f"DO_VentiladorCondensador_2 = {'ON' if self.ventilador_2 else 'OFF'}")
