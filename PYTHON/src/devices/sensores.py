# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : sensores.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.2
#
# DESCRICAO
# --------------------------------------------------------------
# Simulacao dos sensores da maquina frigorifica.
#
# IMPORTANTE:
# Estes valores variam somente para testar a logica no Python.
#
# No ISaGRAF, as temperaturas e pressoes serao recebidas
# diretamente dos sensores instalados na maquina.
# ==============================================================


class Sensores:
    """
    Simulacao das temperaturas e pressoes da maquina.
    """

    def __init__(self):
        """
        Define os valores iniciais da simulacao.
        """

        self.temp_camara = -15.0
        self.temp_evaporador = -22.0

        self.pressao_succao = 18.0
        self.pressao_descarga = 260.0
        self.pressao_oleo = 45.0

    def atualizar(self, compressor_ligado):
        """
        Atualiza os sensores durante o funcionamento normal.

        Compressor ligado:
            - A camara resfria;
            - O evaporador resfria;
            - A succao diminui;
            - A descarga aumenta.

        Compressor desligado:
            - A camara aquece lentamente;
            - O evaporador retorna gradualmente;
            - A succao aumenta;
            - A descarga diminui.
        """

        if compressor_ligado:
            self.temp_camara = max(
                -35.0,
                self.temp_camara - 0.3
            )

            self.temp_evaporador = max(
                -45.0,
                self.temp_evaporador - 0.5
            )

            self.pressao_succao = max(
                0.0,
                self.pressao_succao - 0.2
            )

            self.pressao_descarga = min(
                350.0,
                self.pressao_descarga + 0.5
            )

        else:
            self.temp_camara = min(
                25.0,
                self.temp_camara + 0.2
            )

            if self.temp_evaporador > 0.0:
                self.temp_evaporador = max(
                    0.0,
                    self.temp_evaporador - 0.4
                )

            else:
                self.temp_evaporador = min(
                    10.0,
                    self.temp_evaporador + 0.3
                )

            self.pressao_succao = min(
                60.0,
                self.pressao_succao + 0.2
            )

            self.pressao_descarga = max(
                0.0,
                self.pressao_descarga - 0.5
            )

    def atualizar_pos_degelo(self, compressor_ligado):
        """
        Atualiza os sensores durante o resfriamento
        do evaporador depois do degelo.

        Nesse momento, o ventilador do evaporador permanece
        desligado. Por isso, o evaporador resfria, mas a
        temperatura da camara praticamente nao diminui.

        Compressor ligado:
            - O evaporador resfria;
            - A camara permanece praticamente estavel;
            - A succao diminui;
            - A descarga aumenta.

        Compressor desligado:
            - O evaporador permanece quente ou aquece;
            - A camara aquece lentamente;
            - As pressoes retornam gradualmente.
        """

        if compressor_ligado:
            # Evaporador resfriando depois do degelo.
            self.temp_evaporador = max(
                -45.0,
                self.temp_evaporador - 0.5
            )

            # Como o ventilador esta desligado, o frio ainda
            # nao esta sendo distribuido pela camara.
            self.temp_camara = min(
                25.0,
                self.temp_camara + 0.02
            )

            self.pressao_succao = max(
                0.0,
                self.pressao_succao - 0.2
            )

            self.pressao_descarga = min(
                350.0,
                self.pressao_descarga + 0.5
            )

        else:
            # Durante o anti-rearme, o evaporador ainda
            # nao esta sendo resfriado pelo compressor.
            if self.temp_evaporador > 0.0:
                self.temp_evaporador = max(
                    0.0,
                    self.temp_evaporador - 0.1
                )

            else:
                self.temp_evaporador = min(
                    10.0,
                    self.temp_evaporador + 0.1
                )

            self.temp_camara = min(
                25.0,
                self.temp_camara + 0.02
            )

            self.pressao_succao = min(
                60.0,
                self.pressao_succao + 0.2
            )

            self.pressao_descarga = max(
                0.0,
                self.pressao_descarga - 0.5
            )

    def exibir(self):
        """
        Exibe os valores atuais dos sensores.
        """

        print(
            f"\nCamara={self.temp_camara:.1f} C | "
            f"Evaporador={self.temp_evaporador:.1f} C | "
            f"Succao={self.pressao_succao:.1f} PSI | "
            f"Descarga={self.pressao_descarga:.1f} PSI | "
            f"Oleo={self.pressao_oleo:.1f} PSI"
        )

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

    def status(self):
        """
        Retorna todos os valores em formato de dicionario.
        """

        return {
            "temperatura_camara": self.temp_camara,
            "temperatura_evaporador": self.temp_evaporador,
            "pressao_succao": self.pressao_succao,
            "pressao_descarga": self.pressao_descarga,
            "pressao_oleo": self.pressao_oleo,
        }