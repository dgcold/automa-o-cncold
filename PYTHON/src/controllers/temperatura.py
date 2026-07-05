class TemperaturaController:

    def __init__(self):

        self.setpoint = -18.0
        self.diferencial = 2.0

    def precisa_refrigerar(self, temperatura):

        return temperatura > (
            self.setpoint + self.diferencial
        )

    def atingiu_setpoint(self, temperatura):

        return temperatura <= self.setpoint
    def __init__(self, setpoint=-18, diferencial=2):
        self.setpoint = setpoint
        self.diferencial = diferencial

    def precisa_refrigerar(self, temperatura_atual):
        return temperatura_atual > self.setpoint + self.diferencial

    def atingiu_setpoint(self, temperatura_atual):
        return temperatura_atual <= self.setpoint
