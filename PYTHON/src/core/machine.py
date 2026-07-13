# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : machine.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Modulo principal da maquina de estados da camara frigorifica.
#
# Este arquivo coordena:
#
#   - Inicializacao do sistema
#   - Verificacao das protecoes
#   - Controle de temperatura
#   - Refrigeracao
#   - Anti-rearme do compressor
#   - Ventiladores
#   - Linha de liquido
#   - Valvula de expansao
#   - Degelo por gas quente
#   - Gotejamento
#   - Alarmes
#   - Finalizacao segura
# ==============================================================

import time

from config.machine_config import MachineConfig
from core.states import MachineState
from core.timer import Timer

from controllers.alarmes import AlarmesController
from controllers.oleo import OleoController
from controllers.partida import PartidaController
from controllers.seguranca import SegurancaController
from controllers.temperatura import TemperaturaController

from devices.compressor import Compressor
from devices.condensador import Condensador
from devices.degelo import Degelo
from devices.evaporador import Evaporador
from devices.linha_liquida import LinhaLiquida
from devices.sensores import Sensores
from devices.solenoide_gas_quente import SolenoideGasQuente
from devices.valvula_expansao import ValvulaExpansao


class Machine:
    """
    Classe principal da maquina frigorifica.
    """

    def __init__(self):
        self.estado_atual = MachineState.ST_DESLIGADA

        self.timer_degelo = Timer()

        self.seguranca = SegurancaController()
        self.temperatura = TemperaturaController()
        self.alarmes = AlarmesController()
        self.partida = PartidaController()
        self.oleo = OleoController()

        self.sensores = Sensores()

        self.compressor = Compressor()
        self.condensador = Condensador()
        self.evaporador = Evaporador()
        self.degelo = Degelo()
        self.linha_liquida = LinhaLiquida()
        self.gas_quente = SolenoideGasQuente()
        self.valvula_expansao = ValvulaExpansao()

        self.entradas = {
            "DI_PartidaRemota": True,
            "DI_ProtecaoEnergia": True,
            "DI_FalhaEvaporador": False,
            "DI_FalhaCondensador": False,
            "DI_TermicoCompressor": False,
            "DI_PressostatoAlta": False,
            "DI_PressostatoBaixa": False,
            "DI_PressostatoOleo": False,
            "DI_FluxostatoCondensacao": False,
            "DI_Emergencia": False,
        }

    def alterar_estado(self, novo_estado):
        """
        Atualiza o estado da maquina somente quando houver
        mudanca real.
        """

        if self.estado_atual != novo_estado:
            self.estado_atual = novo_estado

            print(
                f"\nEstado da maquina: "
                f"{self.estado_atual.value}"
            )

    def iniciar(self):
        """
        Inicia a aplicacao e executa o ciclo principal.
        """

        print("CNCOLD Automation Framework iniciado.")

        self.alterar_estado(
            MachineState.ST_INICIALIZANDO
        )

        self.timer_degelo.iniciar()

        try:
            while True:
                liberada = self.verificar_seguranca()

                if (
                    liberada
                    and self.timer_degelo.expirou(
                        MachineConfig.INTERVALO_DEGELO_SEGUNDOS
                    )
                ):
                    self.executar_degelo()
                    self.timer_degelo.reiniciar()

                self.sensores.atualizar(
                    self.compressor.ligado
                )

                time.sleep(1)

        except KeyboardInterrupt:
            self.finalizar()

            print(
                "\nSistema finalizado pelo operador."
            )

    def verificar_seguranca(self):
        """
        Verifica as protecoes antes de permitir o funcionamento.
        """

        self.sensores.exibir()

        alarmes = self.seguranca.verificar(
            self.entradas
        )

        oleo_ok = self.oleo.verificar(
            self.compressor.ligado,
            self.entradas.get(
                "DI_PressostatoOleo",
                False
            ),
        )

        if not oleo_ok:
            alarmes.append(
                "Falha de pressao de oleo"
            )

        self.alarmes.limpar()

        for alarme in alarmes:
            self.alarmes.adicionar(alarme)

        if not self.partida.liberar(alarmes):
            self.parar_refrigeracao()

            self.alterar_estado(
                MachineState.ST_ALARME
            )

            return False

        self.controlar_temperatura()

        return True

    def controlar_temperatura(self):
        """
        Controla a refrigeracao conforme setpoint e diferencial.
        """

        temperatura = self.sensores.temp_camara

        # ======================================================
        # PEDIDO DE REFRIGERACAO
        # ======================================================

        if self.temperatura.precisa_refrigerar(
            temperatura
        ):
            self.alterar_estado(
                MachineState.ST_REFRIGERANDO
            )

            if (
                not self.compressor.pode_ligar()
                and not self.compressor.ligado
            ):
                self.condensador.controlar(
                    False,
                    self.sensores.pressao_descarga
                )

                self.evaporador.controlar(
                    False,
                    self.degelo.ativo
                )

                print("Aguardando anti-rearme.")

                return

            self.linha_liquida.ligar()
            self.valvula_expansao.posicionar(100)

            compressor_ligou = self.compressor.ligar()

            if compressor_ligou:
                self.condensador.controlar(
                    True,
                    self.sensores.pressao_descarga
                )

                self.evaporador.controlar(
                    True,
                    self.degelo.ativo
                )

        # ======================================================
        # SETPOINT ATINGIDO
        # ======================================================

        elif self.temperatura.atingiu_setpoint(
            temperatura
        ):
            print("Setpoint atingido.")

            self.parar_refrigeracao()

            self.alterar_estado(
                MachineState.ST_PRONTA
            )

        # ======================================================
        # FAIXA DE HISTERESE
        #
        # Se o compressor ainda estiver ligado, a maquina
        # permanece em REFRIGERANDO.
        #
        # Se o compressor estiver desligado, permanece PRONTA.
        # ======================================================

        else:
            if self.compressor.ligado:
                self.alterar_estado(
                    MachineState.ST_REFRIGERANDO
                )
            else:
                self.alterar_estado(
                    MachineState.ST_PRONTA
                )

            self.condensador.controlar(
                self.compressor.ligado,
                self.sensores.pressao_descarga
            )

            self.evaporador.controlar(
                self.compressor.ligado,
                self.degelo.ativo
            )

    def executar_degelo(self):
        """
        Executa o ciclo de degelo por gas quente.
        """

        print("\n***** INICIANDO DEGELO *****")

        self.alterar_estado(
            MachineState.ST_DEGELO
        )

        self.parar_refrigeracao()

        self.degelo.iniciar()
        self.gas_quente.ligar()

        abertura = (
            MachineConfig.ABERTURA_INICIAL_DEGELO
        )

        self.valvula_expansao.posicionar(
            abertura
        )

        inicio = time.monotonic()

        while True:
            self.evaporador.controlar(
                False,
                True
            )

            temperatura_evaporador = (
                self.sensores.temp_evaporador
            )

            if self.degelo.deve_finalizar(
                temperatura_evaporador
            ):
                print(
                    "Temperatura final de degelo atingida."
                )

                break

            tempo_decorrido = (
                time.monotonic() - inicio
            )

            if (
                tempo_decorrido
                >= MachineConfig.TEMPO_MAXIMO_DEGELO_SEGUNDOS
            ):
                print(
                    "Tempo maximo de degelo atingido."
                )

                break

            time.sleep(
                MachineConfig.PASSO_VALVULA_DEGELO_SEGUNDOS
            )

            abertura = min(
                100,
                abertura
                + MachineConfig.INCREMENTO_VALVULA_DEGELO
            )

            self.valvula_expansao.posicionar(
                abertura
            )

            self.sensores.temp_evaporador += 3.0

            print(
                "Temperatura evaporador no degelo: "
                f"{self.sensores.temp_evaporador:.1f} C"
            )

        self.valvula_expansao.fechar()
        self.gas_quente.desligar()
        self.degelo.finalizar()

        print("***** FIM DO DEGELO *****")

        self.executar_gotejamento()

    def executar_gotejamento(self):
        """
        Executa o periodo de gotejamento.
        """

        print(
            "\n***** INICIANDO GOTEJAMENTO *****"
        )

        self.alterar_estado(
            MachineState.ST_GOTEJAMENTO
        )

        self.compressor.desligar()
        self.linha_liquida.desligar()
        self.valvula_expansao.fechar()
        self.gas_quente.desligar()

        self.condensador.controlar(
            False,
            self.sensores.pressao_descarga
        )

        self.evaporador.controlar(
            False,
            True
        )

        tempo_restante = (
            MachineConfig.TEMPO_GOTEJAMENTO_SEGUNDOS
        )

        while tempo_restante > 0:
            print(
                "Gotejamento: "
                f"{tempo_restante} segundos restantes"
            )

            time.sleep(1)
            tempo_restante -= 1

        print(
            "***** FIM DO GOTEJAMENTO *****"
        )

        self.alterar_estado(
            MachineState.ST_PRONTA
        )

    def parar_refrigeracao(self):
        """
        Desliga todos os dispositivos da refrigeracao.
        """

        self.linha_liquida.desligar()
        self.valvula_expansao.fechar()
        self.compressor.desligar()

        self.condensador.controlar(
            False,
            self.sensores.pressao_descarga
        )

        self.evaporador.controlar(
            False,
            self.degelo.ativo
        )

    def finalizar(self):
        """
        Finaliza o sistema com todas as saidas desligadas.
        """

        self.parar_refrigeracao()

        self.gas_quente.desligar()
        self.degelo.finalizar()

        self.alterar_estado(
            MachineState.ST_DESLIGADA
        )