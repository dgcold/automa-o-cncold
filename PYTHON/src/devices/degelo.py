class Degelo:

    def __init__(self):
        self.ativo = False
        self.temperatura_fim = 8.0

    def iniciar(self):
        self.ativo = True
        print("DO_Degelo = ON")

    def finalizar(self):
        self.ativo = False
        print("DO_Degelo = OFF")

    def deve_finalizar(self, temperatura_evaporador):
        return temperatura_evaporador >= self.temperatura_fim