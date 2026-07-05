class AlarmesController:

    def __init__(self):
        self.alarmes = []

    def adicionar(self, mensagem):
        if mensagem not in self.alarmes:
            self.alarmes.append(mensagem)

    def remover(self, mensagem):
        if mensagem in self.alarmes:
            self.alarmes.remove(mensagem)

    def limpar(self):
        self.alarmes.clear()

    def existe_alarme(self):
        return len(self.alarmes) > 0

    def listar(self):
        return self.alarmes