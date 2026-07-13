# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : sensores.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Simulacao dos sensores da camara frigorifica.
#
# Sensores simulados:
#
# • Temperatura da camara
# • Temperatura do evaporador
# • Pressao de succao
# • Pressao de descarga
# • Pressao de oleo
#
# Os valores sao atualizados automaticamente conforme o estado
# do compressor, permitindo validar toda a logica da maquina.
# ==============================================================


class Sensores:
    """
    Simulacao dos sensores da maquina.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa os valores simulados dos sensores.
        """

        self.temp_camara = -15.0
        self.temp_evaporador = -22.0

        self.pressao_succao = 28.0
        self.pressao_descarga = 260.0
        self.pressao_oleo = 45.0

    # ==========================================================
    # ATUALIZACAO DOS SENSORES
    # ==========================================================

    def atualizar(self, compressor_ligado):
        """
        Atualiza os sensores de acordo com o estado do compressor.

        Compressor ligado:

            • Camara esfria
            • Evaporador esfria
            • Succao diminui
            • Descarga aumenta

        Compressor desligado:

            • Camara aquece lentamente
            • Evaporador aquece
            • Succao aumenta
            • Descarga diminui
        """

        if compressor_ligado:

            # Refrigeração

            self.temp_camara -= 0.3
            self.temp_evaporador -= 0.5

            self.pressao_succao = max(
                0.0,
                self.pressao_succao - 0.2
            )

            self.pressao_descarga += 0.5

        else:

            # Sistema parado

            self.temp_camara += 0.2
            self.temp_evaporador += 0.3

            self.pressao_succao += 0.2

            self.pressao_descarga = max(
                0.0,
                self.pressao_descarga - 0.5
            )

    # ==========================================================
    # EXIBICAO DOS SENSORES
    # ==========================================================

    def exibir(self):
        """
        Exibe todos os sensores simulados.
        """

        print(
            f"\nCamara={self.temp_camara:.1f} C | "
            f"Evaporador={self.temp_evaporador:.1f} C | "
            f"Succao={self.pressao_succao:.1f} bar | "
            f"Descarga={self.pressao_descarga:.1f} PSI | "
            f"Oleo={self.pressao_oleo:.1f} PSI"
        )

    # ==========================================================
    # LEITURA DOS SENSORES
    # ==========================================================

    def ler_temperatura_camara(self):
        """
        Retorna a temperatura da camara.
        """
        return self.temp_camara

    def ler_temperatura_evaporador(self):
        """
        Retorna a temperatura do evaporador.
        """
        return self.temp_evaporador

    def ler_pressao_succao(self):
        """
        Retorna a pressao de succao.
        """
        return self.pressao_succao

    def ler_pressao_descarga(self):
        """
        Retorna a pressao de descarga.
        """
        return self.pressao_descarga

    def ler_pressao_oleo(self):
        """
        Retorna a pressao de oleo.
        """
        return self.pressao_oleo

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna todos os sensores em formato de dicionario.
        """

        return {
            "temperatura_camara": self.temp_camara,
            "temperatura_evaporador": self.temp_evaporador,
            "pressao_succao": self.pressao_succao,
            "pressao_descarga": self.pressao_descarga,
            "pressao_oleo": self.pressao_oleo,
        }