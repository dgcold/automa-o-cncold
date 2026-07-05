class Evaporador:

    def __init__(self):
        self.ligado = False

    def controlar(self, compressor_ligado, degelo_ativo):

        if compressor_ligado and not degelo_ativo:
            self.ligado = True
        else:
            self.ligado = False

        print(f"DO_VentiladorEvaporador = {'ON' if self.ligado else 'OFF'}")
