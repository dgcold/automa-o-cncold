# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : evaporador.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo controle do ventilador do evaporador.
#
# Regras de funcionamento:
#
# • Compressor ligado:
#       Ventilador ligado.
#
# • Degelo ativo:
#       Ventilador desligado.
#
# • Compressor desligado:
#       Ventilador desligado.
#
# O ventilador nunca deve operar durante o degelo para evitar
# que o calor seja distribuido para a camara.
# ==============================================================


class Evaporador:
    """
    Controle do ventilador do evaporador.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa o ventilador do evaporador.
        """

        self.ligado = False

    # ==========================================================
    # CONTROLE DO VENTILADOR
    # ==========================================================

    def controlar(
        self,
        compressor_ligado,
        degelo_ativo
    ):
        """
        Controla o ventilador do evaporador.

        Regras:

            Compressor ON
            Degelo OFF

                -> Ventilador ON

            Compressor OFF

                -> Ventilador OFF

            Degelo ON

                -> Ventilador OFF
        """

        # ------------------------------------------------------
        # REFRIGERACAO
        # ------------------------------------------------------

        if compressor_ligado and not degelo_ativo:

            self.ligado = True

        # ------------------------------------------------------
        # DEGELO OU COMPRESSOR DESLIGADO
        # ------------------------------------------------------

        else:

            self.ligado = False

        print(
            "DO_VentiladorEvaporador = "
            f"{'ON' if self.ligado else 'OFF'}"
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna o estado atual do ventilador.
        """

        return self.ligado