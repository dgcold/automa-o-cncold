# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : timer.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Temporizador utilizado em toda a aplicacao.
#
# Aplicacoes:
#
# • Anti-rearme do compressor
# • Intervalo entre degelos
# • Protecao de oleo
# • Gotejamento
# • Temporizadores futuros
#
# O temporizador utiliza time.monotonic(), evitando erros
# causados pela alteracao do relogio do sistema operacional.
# ==============================================================

import time


class Timer:
    """
    Temporizador generico da aplicacao.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o temporizador.
        """

        self.inicio = None

    # ==========================================================
    # INICIAR
    # ==========================================================

    def iniciar(self):
        """
        Inicia a contagem do tempo.
        """

        self.inicio = time.monotonic()

    # ==========================================================
    # REINICIAR
    # ==========================================================

    def reiniciar(self):
        """
        Reinicia o temporizador.
        """

        self.iniciar()

    # ==========================================================
    # PARAR
    # ==========================================================

    def parar(self):
        """
        Interrompe o temporizador.
        """

        self.inicio = None

    # ==========================================================
    # VERIFICAR TEMPO
    # ==========================================================

    def expirou(self, segundos):
        """
        Verifica se o tempo configurado foi atingido.

        Parametro:

            segundos
                Tempo desejado.

        Retorno:

            True
                Tempo expirado.

            False
                Tempo ainda nao atingido.
        """

        if self.inicio is None:
            return False

        return (
            time.monotonic() - self.inicio
        ) >= segundos

    # ==========================================================
    # TEMPO DECORRIDO
    # ==========================================================

    def tempo_decorrido(self):
        """
        Retorna o tempo transcorrido desde o inicio.

        Retorno:

            Tempo em segundos.
        """

        if self.inicio is None:
            return 0.0

        return (
            time.monotonic() - self.inicio
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    def ativo(self):
        """
        Verifica se o temporizador esta ativo.

        Retorno:

            True
                Temporizador iniciado.

            False
                Temporizador parado.
        """

        return self.inicio is not None