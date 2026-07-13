class PartidaController:
    def __init__(self):
        self.habilitado = True

    def liberar(self, alarmes):
        self.habilitado = len(alarmes) == 0
        return self.habilitado
