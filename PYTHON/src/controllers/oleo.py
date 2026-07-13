from config.machine_config import MachineConfig
from core.timer import Timer


class OleoController:
    def __init__(self):
        self.timer = Timer()

    def verificar(self, compressor_ligado, pressostato_oleo_atuado):
        if not compressor_ligado:
            self.timer.parar()
            return True

        if not pressostato_oleo_atuado:
            self.timer.parar()
            return True

        if self.timer.inicio is None:
            self.timer.iniciar()

        return not self.timer.expirou(MachineConfig.TEMPO_MAXIMO_OLEO_SEGUNDOS)
