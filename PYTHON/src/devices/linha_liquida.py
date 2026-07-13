class LinhaLiquida:
    def __init__(self):
        self.ligada = False

    def ligar(self):
        if not self.ligada:
            self.ligada = True
            print("DO_LinhaLiquida = ON")

    def desligar(self):
        if self.ligada:
            self.ligada = False
            print("DO_LinhaLiquida = OFF")
