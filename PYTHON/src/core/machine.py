# -*- coding: utf-8 -*-
from core.states import MachineState
from controllers.seguranca import SegurancaController
from controllers.temperatura import TemperaturaController
from devices.compressor import Compressor
from devices.condensador import Condensador
from devices.evaporador import Evaporador
from devices.degelo import Degelo
from devices.sensores import Sensores


class Machine:
    def __init__(self):
        self.estado_atual = MachineState.ST_DESLIGADA

        self.seguranca = SegurancaController()
        self.temperatura = TemperaturaController()

        self.sensores = Sensores()

        self.compressor = Compressor()
        self.condensador = Condensador()
        self.evaporador = Evaporador()
        self.degelo = Degelo()

        self.entradas = {
            "DI_PartidaRemota": True,
            "DI_ProtecaoEnergia": True,
            "DI_FalhaEvaporador": False,
            "DI_FalhaCondensador": False,
            "DI_TermicoCompressor": False,
            "DI_PressostatoAlta": False,
            "DI_PressostatoBaixa": False,
            "DI_PressostatoOleo": False,
        }

    def alterar_estado(self, novo_estado):
        self.estado_atual = novo_estado
        print(f"Estado da maquina: {self.estado_atual.value}")

    def iniciar(self):
        print("CNCOLD Automation Framework iniciado.")
        self.alterar_estado(MachineState.ST_INICIALIZANDO)
        self.verificar_seguranca()

    def verificar_seguranca(self):
        self.alterar_estado(MachineState.ST_VERIFICANDO)

        alarmes = self.seguranca.verificar(self.entradas)

        if len(alarmes) > 0:
            print("Falha de seguranca.")

            for alarme in alarmes:
                print(f"ALARME: {alarme}")

            self.parar_refrigeracao()
            self.alterar_estado(MachineState.ST_ALARME)
            return

        print("Seguranca OK.")
        self.alterar_estado(MachineState.ST_PRONTA)
        self.controlar_temperatura()

    def controlar_temperatura(self):
        temp_camara = self.sensores.ler_temperatura_camara()
        pressao_descarga = self.sensores.ler_pressao_descarga()

        print(f"Temperatura da camara: {temp_camara} C")
        print(f"Pressao de descarga: {pressao_descarga} PSI")

        if self.temperatura.precisa_refrigerar(temp_camara):
            self.alterar_estado(MachineState.ST_REFRIGERANDO)

            self.compressor.ligar()

            self.condensador.controlar(
                self.compressor.ligado,
                pressao_descarga
            )

            self.evaporador.controlar(
                self.compressor.ligado,
                self.degelo.ativo
            )

        else:
            print("Temperatura dentro do setpoint.")
            self.parar_refrigeracao()

    def parar_refrigeracao(self):
        self.compressor.desligar()

        self.condensador.controlar(
            False,
            self.sensores.ler_pressao_descarga()
        )

        self.evaporador.controlar(
            False,
            self.degelo.ativo
        )