class SolenoideGasQuente:
    def __init__(self):
        self.ligada = False

    def ligar(self):
        if not self.ligada:
            self.ligada = True
            print("DO_GasQuente = ON")

    def desligar(self):
        if self.ligada:
            self.ligada = False
            print("DO_GasQuente = OFF")
