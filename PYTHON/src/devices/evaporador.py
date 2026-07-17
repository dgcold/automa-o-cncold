# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : evaporador.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.2
#
# DESCRICAO
# --------------------------------------------------------------
# Controle dos ventiladores do evaporador.
#
# Os ventiladores possuem comando independente do compressor.
#
# Eles podem permanecer ligados durante a refrigeracao,
# mesmo quando o compressor estiver parado por setpoint.
#
# Devem permanecer desligados durante:
#
#   - Degelo
#   - Gotejamento
#   - Alarme
#   - Maquina desligada
# ==============================================================


class Evaporador:
    """
    Controle da saida dos ventiladores do evaporador.
    """

    def __init__(self):
        """
        Inicializa os ventiladores desligados.
        """

        self.ligado = False

    def controlar(
        self,
        maquina_liberada,
        degelo_ativo=False,
        gotejamento_ativo=False
    ):
        """
        Atualiza o estado dos ventiladores.

        maquina_liberada:
            True quando a maquina esta ligada e sem alarmes.

        degelo_ativo:
            True durante o ciclo de degelo.

        gotejamento_ativo:
            True durante o periodo de gotejamento.
        """

        estado_anterior = self.ligado

        self.ligado = (
            maquina_liberada
            and not degelo_ativo
            and not gotejamento_ativo
        )

        if estado_anterior != self.ligado:
            print(
                "DO_VentiladorEvaporador = "
                f"{'ON' if self.ligado else 'OFF'}"
            )

    def ligar(self):
        """
        Liga os ventiladores do evaporador.
        """

        if self.ligado:
            return True

        self.ligado = True

        print("DO_VentiladorEvaporador = ON")

        return True

    def desligar(self):
        """
        Desliga os ventiladores do evaporador.
        """

        if not self.ligado:
            return False

        self.ligado = False

        print("DO_VentiladorEvaporador = OFF")

        return True

    def esta_ligado(self):
        """
        Retorna o estado atual dos ventiladores.
        """

        return self.ligado

    def status(self):
        """
        Retorna as informacoes dos ventiladores.
        """

        return {
            "ligado": self.ligado
        }