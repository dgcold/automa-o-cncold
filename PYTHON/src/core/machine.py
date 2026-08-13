# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : machine.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.5
#
# DESCRICAO
# --------------------------------------------------------------
# Modulo principal da maquina frigorifica.
#
# Logica principal:
#
#   - Compressor controlado pelo setpoint da camara
#   - Ventilador do evaporador independente do compressor
#   - Ventilador permanece ligado quando atinge o setpoint
#   - Ventilador desligado durante o degelo
#   - Ventilador desligado durante o gotejamento
#   - Ventilador desligado em caso de alarme
#   - Compressor resfria o evaporador depois do degelo
#   - Ventilador liberado pela temperatura do evaporador
#   - Liberacao alternativa por tempo maximo
#   - Retorno ao controle normal depois da liberacao
#   - Degelo realizado pela solenoide de gas quente
#   - Valvula de expansao fechada durante o degelo
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
        """
        Inicializa controladores, dispositivos, sensores
        e entradas digitais.
        """

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
        Atualiza o estado da maquina somente quando
        houver mudanca.
        """

        if self.estado_atual == novo_estado:
            return

        self.estado_atual = novo_estado

        print(
            f"\nEstado da maquina: "
            f"{self.estado_atual.value}"
        )

    def iniciar(self):
        """
        Inicia o ciclo principal da maquina.
        """

        print("CNCOLD Automation Framework iniciado.")

        self.alterar_estado(
            MachineState.ST_INICIALIZANDO
        )

        self.timer_degelo.iniciar()

        try:
            while True:
                maquina_liberada = (
                    self.verificar_seguranca()
                )

                if (
                    maquina_liberada
                    and self.timer_degelo.expirou(
                        MachineConfig
                        .INTERVALO_DEGELO_SEGUNDOS
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
        Verifica protecoes digitais e pressao de oleo.
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
            self.parar_por_alarme()

            self.alterar_estado(
                MachineState.ST_ALARME
            )

            return False

        self.controlar_temperatura()

        return True

    def controlar_temperatura(self):
        """
        Controla a refrigeracao pelo setpoint
        e diferencial da camara.

        O ventilador do evaporador possui comando
        independente do compressor.
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

            self.evaporador.controlar(
                True,
                False,
                False
            )

            if (
                not self.compressor.pode_ligar()
                and not self.compressor.ligado
            ):
                self.linha_liquida.desligar()
                self.valvula_expansao.fechar()

                self.condensador.controlar(
                    False,
                    self.sensores.pressao_descarga
                )

                print("Aguardando anti-rearme.")

                return

            self.linha_liquida.ligar()

            self.valvula_expansao.posicionar(
                100
            )

            compressor_ligou = (
                self.compressor.ligar()
            )

            self.condensador.controlar(
                compressor_ligou,
                self.sensores.pressao_descarga
            )

            return

        # ======================================================
        # SETPOINT ATINGIDO
        # ======================================================

        if self.temperatura.atingiu_setpoint(
            temperatura
        ):
            if self.compressor.ligado:
                print("Setpoint atingido.")

            self.parar_por_setpoint()

            self.alterar_estado(
                MachineState.ST_PRONTA
            )

            return

        # ======================================================
        # FAIXA DE HISTERESE
        # ======================================================

        if self.compressor.ligado:
            self.alterar_estado(
                MachineState.ST_REFRIGERANDO
            )

            self.linha_liquida.ligar()

            self.valvula_expansao.posicionar(
                100
            )

            self.condensador.controlar(
                True,
                self.sensores.pressao_descarga
            )

        else:
            self.alterar_estado(
                MachineState.ST_PRONTA
            )

            self.linha_liquida.desligar()
            self.valvula_expansao.fechar()

            self.condensador.controlar(
                False,
                self.sensores.pressao_descarga
            )

        self.evaporador.controlar(
            True,
            False,
            False
        )

    def parar_por_setpoint(self):
        """
        Para o compressor ao atingir o setpoint.

        O ventilador do evaporador permanece ligado.
        """

        self.linha_liquida.desligar()
        self.valvula_expansao.fechar()
        self.compressor.desligar()

        self.condensador.controlar(
            False,
            self.sensores.pressao_descarga
        )

        self.evaporador.controlar(
            True,
            False,
            False
        )

    def executar_degelo(self):
        """
        Executa o degelo pela solenoide
        de gas quente.
        """

        print("\n***** INICIANDO DEGELO *****")

        self.alterar_estado(
            MachineState.ST_DEGELO
        )

        self.parar_para_degelo()

        self.degelo.iniciar()
        self.gas_quente.ligar()

        inicio = time.monotonic()

        while True:
            self.evaporador.controlar(
                False,
                True,
                False
            )

            temperatura_evaporador = (
                self.sensores.temp_evaporador
            )

            if self.degelo.deve_finalizar(
                temperatura_evaporador
            ):
                print(
                    "Temperatura final de degelo "
                    "atingida."
                )

                break

            tempo_decorrido = (
                time.monotonic() - inicio
            )

            if (
                tempo_decorrido
                >= MachineConfig
                .TEMPO_MAXIMO_DEGELO_SEGUNDOS
            ):
                print(
                    "Tempo maximo de degelo atingido."
                )

                break

            time.sleep(
                MachineConfig
                .PASSO_SIMULACAO_DEGELO_SEGUNDOS
            )

            # Atualizacao utilizada somente na simulacao.
            self.sensores.temp_evaporador += 3.0

            print(
                "Temperatura evaporador no degelo: "
                f"{self.sensores.temp_evaporador:.1f} C"
            )

        self.gas_quente.desligar()
        self.degelo.finalizar()

        print("***** FIM DO DEGELO *****")

        self.executar_gotejamento()

    def parar_para_degelo(self):
        """
        Desliga o circuito de refrigeracao antes
        de iniciar o degelo.
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
            True,
            False
        )

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
            False,
            True
        )

        tempo_restante = (
            MachineConfig
            .TEMPO_GOTEJAMENTO_SEGUNDOS
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

        self.aguardar_resfriamento_evaporador()

    def aguardar_resfriamento_evaporador(self):
        """
        Resfria o evaporador depois do degelo antes
        de liberar o ventilador.

        Durante este periodo:

            - Compressor ligado
            - Linha liquida ligada
            - Valvula de expansao aberta
            - Condensador ligado
            - Ventilador do evaporador desligado

        O ventilador sera liberado quando:

            - O evaporador atingir a temperatura configurada;
              ou

            - O tempo maximo de espera for atingido.

        Depois da liberacao, o metodo termina e devolve
        o controle ao ciclo principal da maquina.
        """

        print(
            "\n***** RESFRIAMENTO DO EVAPORADOR *****"
        )

        self.alterar_estado(
            MachineState.ST_REFRIGERANDO
        )

        self.evaporador.controlar(
            False,
            False,
            True
        )

        inicio_espera = time.monotonic()

        while True:
            # ==================================================
            # VERIFICACAO DAS PROTECOES
            # ==================================================

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

            if alarmes:
                self.alarmes.limpar()

                for alarme in alarmes:
                    self.alarmes.adicionar(alarme)

                print(
                    "Resfriamento interrompido "
                    "por alarme."
                )

                self.parar_por_alarme()

                self.alterar_estado(
                    MachineState.ST_ALARME
                )

                return

            # ==================================================
            # PARTIDA DO COMPRESSOR
            # ==================================================

            if not self.compressor.ligado:
                if self.compressor.pode_ligar():
                    self.linha_liquida.ligar()

                    self.valvula_expansao.posicionar(
                        100
                    )

                    compressor_ligou = (
                        self.compressor.ligar()
                    )

                    self.condensador.controlar(
                        compressor_ligou,
                        self.sensores.pressao_descarga
                    )

                else:
                    self.linha_liquida.desligar()
                    self.valvula_expansao.fechar()

                    self.condensador.controlar(
                        False,
                        self.sensores.pressao_descarga
                    )

                    print(
                        "Aguardando anti-rearme "
                        "apos o degelo."
                    )

            else:
                self.linha_liquida.ligar()

                self.valvula_expansao.posicionar(
                    100
                )

                self.condensador.controlar(
                    True,
                    self.sensores.pressao_descarga
                )

            # Ventilador continua desligado.
            self.evaporador.controlar(
                False,
                False,
                True
            )

            self.sensores.atualizar_pos_degelo(
            self.compressor.ligado
)

            temperatura_evaporador = (
                self.sensores.temp_evaporador
            )

            tempo_decorrido = (
                time.monotonic() - inicio_espera
            )

            print(
                "Resfriando evaporador: "
                f"{temperatura_evaporador:.1f} C | "
                f"Tempo: {tempo_decorrido:.0f} s"
            )

            # ==================================================
            # LIBERACAO POR TEMPERATURA
            # ==================================================

            if (
                temperatura_evaporador
                <= MachineConfig
                .TEMPERATURA_LIBERA_VENTILADOR
            ):
                print(
                    "Temperatura de liberacao "
                    "do ventilador atingida."
                )

                break

            # ==================================================
            # LIBERACAO POR TEMPO MAXIMO
            # ==================================================

            if (
                tempo_decorrido
                >= MachineConfig
                .TEMPO_MAXIMO_ESPERA_VENTILADOR_SEGUNDOS
            ):
                print(
                    "Tempo maximo de espera do "
                    "ventilador atingido."
                )

                break

            time.sleep(1)

        # ======================================================
        # LIBERACAO DO VENTILADOR
        # ======================================================

        self.evaporador.controlar(
            True,
            False,
            False
        )

        print(
            "Ventilador do evaporador liberado "
            "apos o degelo."
        )

        # O compressor deixa de ser forcado por este metodo.
        # O ciclo principal assumira novamente o controle
        # pelo setpoint da camara.

        if self.compressor.ligado:
            self.alterar_estado(
                MachineState.ST_REFRIGERANDO
            )
        else:
            self.alterar_estado(
                MachineState.ST_PRONTA
            )

        return

    def parar_por_alarme(self):
        """
        Desliga todas as saidas devido a alarme.
        """

        self.linha_liquida.desligar()
        self.valvula_expansao.fechar()
        self.compressor.desligar()
        self.gas_quente.desligar()
        self.degelo.finalizar()

        self.condensador.controlar(
            False,
            self.sensores.pressao_descarga
        )

        self.evaporador.controlar(
            False,
            False,
            False
        )

    def parar_refrigeracao(self):
        """
        Desliga completamente o circuito frigorifico.
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
            False,
            False
        )

    def finalizar(self):
        """
        Finaliza o programa com todas as saidas desligadas.
        """

        self.parar_refrigeracao()

        self.gas_quente.desligar()
        self.degelo.finalizar()

        self.alterar_estado(
            MachineState.ST_DESLIGADA
        )