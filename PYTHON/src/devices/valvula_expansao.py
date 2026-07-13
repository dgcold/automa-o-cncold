class ValvulaExpansao:
    def __init__(self):
        self.abertura = 0

    def posicionar(self, percentual):
        percentual = max(0, min(100, int(percentual)))
        if self.abertura != percentual:
            self.abertura = percentual
            print(f"AO_ValvulaExpansao = {self.abertura}%")

    def fechar(self):
        self.posicionar(0)
