class Compressor:

    def __init__(self):
        self.ligado = False

    def ligar(self):
        self.ligado = True
        print("DO_Compressor = ON")

    def desligar(self):
        self.ligado = False
        print("DO_Compressor = OFF")
