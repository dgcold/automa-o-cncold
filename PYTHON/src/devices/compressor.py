# -*- coding: utf-8 -*-

from config.machine_config import MachineConfig
from core.timer import Timer


class Compressor:
    def __init__(self):
        self.ligado = False
        self.timer_antirearme = Timer()
        self.timer_antirearme.iniciar()

    def pode_ligar(self):
        return self.timer_antirearme.expirou(
            MachineConfig.ANTI_REARME_SEGUNDOS
        )

    def ligar(self):
        if self.ligado:
            return True

        if not self.pode_ligar():
            return False

        self.ligado = True
        print("DO_Compressor = ON")
        return True

    def desligar(self):
        if not self.ligado:
            return

        self.ligado = False
        self.timer_antirearme.reiniciar()
        print("DO_Compressor = OFF")