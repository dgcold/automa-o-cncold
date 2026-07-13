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
#   - Refrigeração
#   - Anti-rearme do compressor
#   - Ventiladores
#   - Linha de liquido
#   - Valvula de expansao
#   - Degelo por gas quente
#   - Gotejamento
#   - Alarmes
#   - Finalizacao segura
#
# A logica atual utiliza sensores simulados para validar a
# sequencia antes da integracao com o controlador iPro.
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

    Responsabilidades:

        1. Coordenar os controladores.
        2. Ler as entradas digitais simuladas.
        3. Monitorar os sensores.
        4. Controlar os dispositivos.
        5. Gerenciar os estados da maquina.
        6. Executar refrigeracao, degelo e gotejamento.
        7. Parar o sistema com seguranca em caso de falha.
    """

    # ==========================================================
    # INICIALIZACAO DOS COMPONENTES
    # ==========================================================

    def __init__(self):
        """
        Inicializa os controladores, sensores, dispositivos,
        temporizadores e entradas digitais da maquina.
        """

        # Estado inicial do equipamento.
        self.estado_atual = MachineState.ST_DESLIGADA

        # Temporizador responsavel pelo intervalo entre degelos.
        self.timer_degelo = Timer()

        # ------------------------------------------------------
        # Controladores
        # ------------------------------------------------------

        self.seguranca = SegurancaController()
        self.temperatura = TemperaturaController()
        self.alarmes = AlarmesController()
        self.partida = PartidaController()
        self.oleo = OleoController()

        # ------------------------------------------------------
        # Sensores
        # ------------------------------------------------------

        self.sensores = Sensores()

        # ------------------------------------------------------
        # Dispositivos de saida
        # ------------------------------------------------------

        self.compressor = Compressor()
        self.condensador = Condensador()
        self.evaporador = Evaporador()
        self.degelo = Degelo()
        self.linha_liquida = LinhaLiquida()
        self.gas_quente = SolenoideGasQuente()
        self.valvula_expansao = ValvulaExpansao()

        # ------------------------------------------------------
        # Entradas digitais simuladas
        #
        # Em uma etapa futura, esses valores serao recebidos
        # diretamente do controlador iPro.
        # ------------------------------------------------------

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

    # ==========================================================
    # ALTERACAO DE ESTADO
    # ==========================================================

    def alterar_estado(self, novo_estado):
        """
        Atualiza o estado atual da maquina.

        A mensagem somente e exibida quando ocorre uma mudanca
        real de estado, evitando repeticoes desnecessarias.
        """

        if self.estado_atual != novo_estado:
            self.estado_atual = novo_estado

            print(
                f"\nEstado da maquina: "
                f"{self.estado_atual.value}"
            )

    # ==========================================================
    # INICIALIZACAO E CICLO PRINCIPAL
    # ==========================================================

    def iniciar(self):
        """
        Inicia a aplicacao e executa o ciclo principal.

        Sequencia:

            1. Coloca a maquina em inicializacao.
            2. Inicia o temporizador de degelo.
            3. Verifica continuamente as protecoes.
            4. Controla a temperatura.
            5. Executa o degelo quando o intervalo expira.
            6. Atualiza a simulacao dos sensores.
        """

        print(
            "CNCOLD Automation Framework iniciado."
        )

        self.alterar_estado(
            MachineState.ST_INICIALIZANDO
        )

        # Inicia a contagem para o primeiro degelo.
        self.timer_degelo.iniciar()

        try:
            while True:

                # Verifica as protecoes e controla a maquina.
                liberada = self.verificar_seguranca()

                # Inicia o degelo somente se a maquina estiver
                # liberada e o intervalo tiver expirado.
                if (
                    liberada
                    and self.timer_degelo.expirou(
                        MachineConfig
                        .INTERVALO_DEGELO_SEGUNDOS
                    )
                ):
                    self.executar_degelo()

                    # Reinicia a contagem do proximo degelo.
                    self.timer_degelo.reiniciar()

                # Atualiza os valores dos sensores simulados
                # de acordo com o estado do compressor.
                self.sensores.atualizar(
                    self.compressor.ligado
                )

                # Tempo entre cada ciclo da simulacao.
                time.sleep(1)

        except KeyboardInterrupt:
            # Permite encerrar o programa usando Ctrl + C
            # sem deixar dispositivos simulados ligados.
            self.finalizar()

            print(
                "\nSistema finalizado pelo operador."
            )

    # ==========================================================
    # VERIFICACAO DE SEGURANCA
    # ==========================================================

    def verificar_seguranca(self):
        """
        Verifica as protecoes antes de permitir o funcionamento.

        Protecoes consideradas:

            - Partida remota
            - Protecao de energia
            - Falha do evaporador
            - Falha do condensador
            - Termico do compressor
            - Pressostato de alta
            - Pressostato de baixa
            - Pressostato de oleo
            - Fluxostato
            - Emergencia

        Retorno:

            True:
                Maquina liberada para operar.

            False:
                Existe falha ativa.
        """

        self.alterar_estado(
            MachineState.ST_VERIFICANDO
        )

        # Exibe os valores atuais dos sensores.
        self.sensores.exibir()

        # Verifica as entradas de seguranca.
        alarmes = self.seguranca.verificar(
            self.entradas
        )

        # ------------------------------------------------------
        # PROTECAO DE PRESSAO DE OLEO
        #
        # O controlador de oleo inicia a temporizacao somente
        # quando o compressor esta ligado e existe indicacao
        # de falha do pressostato.
        # ------------------------------------------------------

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

        # Limpa a lista anterior antes de atualizar os alarmes.
        self.alarmes.limpar()

        for alarme in alarmes:
            self.alarmes.adicionar(alarme)

        # Se existir qualquer alarme, a refrigeracao e parada.
        if not self.partida.liberar(alarmes):
            self.parar_refrigeracao()

            self.alterar_estado(
                MachineState.ST_ALARME
            )

            return False

        # Sem alarmes, a maquina pode controlar a temperatura.
        self.controlar_temperatura()

        return True

    # ==========================================================
    # CONTROLE DE TEMPERATURA E REFRIGERACAO
    # ==========================================================

    def controlar_temperatura(self):
        """
        Controla a refrigeracao de acordo com o setpoint.

        Logica:

            Temperatura acima do setpoint + diferencial:
                Inicia refrigeracao.

            Temperatura entre o ponto de ligar e o setpoint:
                Mantem o estado atual dos dispositivos.

            Temperatura igual ou abaixo do setpoint:
                Para a refrigeracao.

        Sequencia de partida:

            1. Verifica o anti-rearme.
            2. Liga a linha de liquido.
            3. Abre a valvula de expansao.
            4. Liga o compressor.
            5. Liga os ventiladores.
        """

        temperatura = self.sensores.temp_camara

        # ------------------------------------------------------
        # PEDIDO DE REFRIGERACAO
        # ------------------------------------------------------

        if self.temperatura.precisa_refrigerar(
            temperatura
        ):
            self.alterar_estado(
                MachineState.ST_REFRIGERANDO
            )

            # O compressor somente pode partir depois do
            # intervalo configurado de anti-rearme.
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

                print(
                    "Aguardando anti-rearme."
                )

                return

            # Abre a linha de liquido antes da partida.
            self.linha_liquida.ligar()

            # Na simulacao, a valvula abre 100%.
            # Futuramente essa abertura sera controlada pelo
            # superaquecimento e pelo algoritmo PID.
            self.valvula_expansao.posicionar(100)

            compressor_ligou = (
                self.compressor.ligar()
            )

            # Os ventiladores somente sao acionados quando
            # o compressor estiver efetivamente ligado.
            if compressor_ligou:
                self.condensador.controlar(
                    True,
                    self.sensores.pressao_descarga
                )

                self.evaporador.controlar(
                    True,
                    self.degelo.ativo
                )

        # ------------------------------------------------------
        # SETPOINT ATINGIDO
        # ------------------------------------------------------

        elif self.temperatura.atingiu_setpoint(
            temperatura
        ):
            print(
                "Setpoint atingido."
            )

            # Desliga todos os equipamentos da refrigeracao.
            self.parar_refrigeracao()

            self.alterar_estado(
                MachineState.ST_PRONTA
            )

        # ------------------------------------------------------
        # FAIXA DE HISTERESE
        #
        # Nesta faixa, a maquina mantem o estado atual para
        # evitar ligamentos e desligamentos muito frequentes.
        # ------------------------------------------------------

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

    # ==========================================================
    # DEGELO POR GAS QUENTE
    # ==========================================================

    def executar_degelo(self):
        """
        Executa o ciclo de degelo por gas quente.

        Sequencia:

            1. Para a refrigeracao.
            2. Mantem o ventilador evaporador desligado.
            3. Liga a saida de degelo.
            4. Liga a solenoide de gas quente.
            5. Abre gradualmente a valvula de expansao.
            6. Monitora a temperatura do evaporador.
            7. Finaliza por temperatura ou tempo maximo.
            8. Inicia o periodo de gotejamento.
        """

        print(
            "\n***** INICIANDO DEGELO *****"
        )

        self.alterar_estado(
            MachineState.ST_DEGELO
        )

        # Garante que o sistema de refrigeracao esteja parado
        # antes de liberar o gas quente.
        self.parar_refrigeracao()

        # Ativa a saida de degelo e a solenoide de gas quente.
        self.degelo.iniciar()
        self.gas_quente.ligar()

        # Define a abertura inicial da valvula no degelo.
        abertura = (
            MachineConfig
            .ABERTURA_INICIAL_DEGELO
        )

        self.valvula_expansao.posicionar(
            abertura
        )

        # Armazena o instante de inicio para controlar o
        # tempo maximo do degelo.
        inicio = time.monotonic()

        while True:

            # O ventilador evaporador deve permanecer desligado
            # durante todo o ciclo de degelo.
            self.evaporador.controlar(
                False,
                True
            )

            temperatura_evaporador = (
                self.sensores.temp_evaporador
            )

            # Finaliza o degelo quando a temperatura configurada
            # for atingida.
            if self.degelo.deve_finalizar(
                temperatura_evaporador
            ):
                print(
                    "Temperatura final de degelo "
                    "atingida."
                )

                break

            # Calcula o tempo transcorrido desde o inicio.
            tempo_decorrido = (
                time.monotonic() - inicio
            )

            # Protecao contra degelo excessivamente longo.
            if (
                tempo_decorrido
                >= MachineConfig
                .TEMPO_MAXIMO_DEGELO_SEGUNDOS
            ):
                print(
                    "Tempo maximo de degelo "
                    "atingido."
                )

                break

            # Aguarda o intervalo entre os passos da valvula.
            time.sleep(
                MachineConfig
                .PASSO_VALVULA_DEGELO_SEGUNDOS
            )

            # Aumenta gradualmente a abertura, limitada a 100%.
            abertura = min(
                100,
                abertura
                + MachineConfig
                .INCREMENTO_VALVULA_DEGELO
            )

            self.valvula_expansao.posicionar(
                abertura
            )

            # Simulacao do aquecimento do evaporador durante
            # a passagem do gas quente.
            self.sensores.temp_evaporador += 3.0

            print(
                "Temperatura evaporador no "
                f"degelo: "
                f"{self.sensores.temp_evaporador:.1f} C"
            )

        # ------------------------------------------------------
        # FINALIZACAO DO DEGELO
        # ------------------------------------------------------

        # Fecha a valvula antes de retirar o gas quente.
        self.valvula_expansao.fechar()

        # Desliga a solenoide de gas quente.
        self.gas_quente.desligar()

        # Desliga a saida de degelo.
        self.degelo.finalizar()

        print(
            "***** FIM DO DEGELO *****"
        )

        # Ao terminar o degelo, inicia automaticamente
        # o periodo de gotejamento.
        self.executar_gotejamento()

    # ==========================================================
    # GOTEJAMENTO
    # ==========================================================

    def executar_gotejamento(self):
        """
        Executa o periodo de gotejamento.

        Objetivo:

            Permitir que a agua formada durante o degelo seja
            drenada antes do retorno da refrigeracao.

        Durante o gotejamento:

            - Compressor desligado
            - Linha de liquido desligada
            - Valvula de expansao fechada
            - Gas quente desligado
            - Ventiladores desligados
        """

        print(
            "\n***** INICIANDO GOTEJAMENTO *****"
        )

        self.alterar_estado(
            MachineState.ST_GOTEJAMENTO
        )

        # Garante que nenhum dispositivo permaneça ligado.
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

        # Carrega o tempo total configurado para gotejamento.
        tempo_restante = (
            MachineConfig
            .TEMPO_GOTEJAMENTO_SEGUNDOS
        )

        # Executa a contagem regressiva.
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

        # Ao terminar o gotejamento, a maquina volta ao estado
        # pronta e aguarda um novo pedido de refrigeracao.
        self.alterar_estado(
            MachineState.ST_PRONTA
        )

    # ==========================================================
    # PARADA DA REFRIGERACAO
    # ==========================================================

    def parar_refrigeracao(self):
        """
        Desliga os dispositivos utilizados na refrigeracao.

        Ordem de desligamento:

            1. Fecha a linha de liquido.
            2. Fecha a valvula de expansao.
            3. Desliga o compressor.
            4. Desliga os ventiladores do condensador.
            5. Desliga o ventilador evaporador.
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

    # ==========================================================
    # FINALIZACAO SEGURA DO SISTEMA
    # ==========================================================

    def finalizar(self):
        """
        Finaliza o programa e garante que todas as saidas
        permaneçam desligadas.

        Este metodo e executado quando o operador encerra
        a aplicacao utilizando Ctrl + C.
        """

        self.parar_refrigeracao()

        self.gas_quente.desligar()
        self.degelo.finalizar()

        self.alterar_estado(
            MachineState.ST_DESLIGADA
        )