import time


class Timer:
    def __init__(self):
        self.inicio = None

    def iniciar(self):
        self.inicio = time.monotonic()

    def reiniciar(self):
        self.iniciar()

    def parar(self):
        self.inicio = None

    def expirou(self, segundos):
        if self.inicio is None:
            return False

        return (time.monotonic() - self.inicio) >= segundos

    def tempo_decorrido(self):
        if self.inicio is None:
            return 0.0

        return time.monotonic() - self.inicio