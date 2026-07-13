from config.machine_config import MachineConfig


class CondensacaoController:
    def __init__(self, fan2_on=None, fan2_off=None):
        self.fan2_on = MachineConfig.FAN2_ON_PSI if fan2_on is None else fan2_on
        self.fan2_off = MachineConfig.FAN2_OFF_PSI if fan2_off is None else fan2_off
        self.fan2_ligado = False

    def segundo_ventilador(self, pressao):
        if not self.fan2_ligado and pressao >= self.fan2_on:
            self.fan2_ligado = True
        elif self.fan2_ligado and pressao <= self.fan2_off:
            self.fan2_ligado = False
        return self.fan2_ligado

    def resetar(self):
        self.fan2_ligado = False
