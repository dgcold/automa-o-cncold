# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : machine_config.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Parametros gerais da maquina frigorifica.
#
# Todas as configuracoes do sistema estao centralizadas neste
# arquivo para facilitar futuras alteracoes.
#
# Parametros:
#
# • Temperatura
# • Anti-rearme
# • Degelo
# • Gotejamento
# • Valvula de expansao
# • Condensacao
# • Protecao de oleo
# ==============================================================


class MachineConfig:

    # ==========================================================
    # CONTROLE DE TEMPERATURA
    # ==========================================================

    # Setpoint da camara (°C)
    SETPOINT = -18.0

    # Diferencial de temperatura (°C)
    DIFERENCIAL = 2.0

    # ==========================================================
    # COMPRESSOR
    # ==========================================================

    # Tempo minimo entre partidas (s)
    ANTI_REARME_SEGUNDOS = 5

    # ==========================================================
    # DEGELO
    # ==========================================================

    # Intervalo entre degelos (s)
    INTERVALO_DEGELO_SEGUNDOS = 60

    # Tempo entre cada abertura da valvula (s)
    PASSO_VALVULA_DEGELO_SEGUNDOS = 2

    # Tempo maximo permitido para o degelo (s)
    TEMPO_MAXIMO_DEGELO_SEGUNDOS = 60

    # Tempo de gotejamento (s)
    TEMPO_GOTEJAMENTO_SEGUNDOS = 10

    # ==========================================================
    # VALVULA DE EXPANSAO
    # ==========================================================

    # Abertura inicial durante o degelo (%)
    ABERTURA_INICIAL_DEGELO = 50

    # Incremento da abertura (%)
    INCREMENTO_VALVULA_DEGELO = 10

    # Temperatura final do evaporador (°C)
    TEMPERATURA_FIM_DEGELO = 8.0

    # ==========================================================
    # CONDENSADOR
    # ==========================================================

    # Liga Fan 2 (PSI)
    FAN2_ON_PSI = 270.0

    # Desliga Fan 2 (PSI)
    FAN2_OFF_PSI = 240.0

    # ==========================================================
    # PROTECAO DE OLEO
    # ==========================================================

    # Tempo maximo sem pressao de oleo (s)
    TEMPO_MAXIMO_OLEO_SEGUNDOS = 30