class MachineConfig:

    # ==========================================================
    # CONTROLE DE TEMPERATURA
    # ==========================================================

    SETPOINT = -18.0
    DIFERENCIAL = 2.0

    # ==========================================================
    # COMPRESSOR
    # ==========================================================

    ANTI_REARME_SEGUNDOS = 5

    # Pressao recomendada de trabalho.
    # Acima deste valor a maquina continua funcionando,
    # apenas perde rendimento.
    PRESSAO_SUCCAO_REFERENCIA_PSI = 20.0

    # ==========================================================
    # DEGELO
    # ==========================================================

    # Intervalo entre degelos
    INTERVALO_DEGELO_SEGUNDOS = 60

    # Tempo maximo do degelo
    TEMPO_MAXIMO_DEGELO_SEGUNDOS = 60

    # Tempo do gotejamento
    TEMPO_GOTEJAMENTO_SEGUNDOS = 10

    # Temperatura para finalizar o degelo
    TEMPERATURA_FIM_DEGELO = 8.0

    # Tempo entre cada atualizacao da simulacao do degelo
    PASSO_SIMULACAO_DEGELO_SEGUNDOS = 2

    # ==========================================================
    # RETARDO DO VENTILADOR APOS DEGELO
    # ==========================================================

    # O ventilador do evaporador so sera liberado
    # quando o evaporador estiver frio novamente.
    TEMPERATURA_LIBERA_VENTILADOR = -5.0

    # Tempo maximo de espera para liberar o ventilador,
    # mesmo que a temperatura ainda nao tenha atingido
    # o valor configurado.
    TEMPO_MAXIMO_ESPERA_VENTILADOR_SEGUNDOS = 120

    # ==========================================================
    # CONDENSADOR
    # ==========================================================

    FAN2_ON_PSI = 270.0
    FAN2_OFF_PSI = 240.0

    # ==========================================================
    # PROTECAO DE OLEO
    # ==========================================================

    TEMPO_MAXIMO_OLEO_SEGUNDOS = 30