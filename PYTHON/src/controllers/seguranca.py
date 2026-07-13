# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : seguranca.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pela verificacao das protecoes da maquina.
#
# Protecoes monitoradas:
#
# • Partida Remota
# • Protecao de Energia
# • Falha do Evaporador
# • Falha do Condensador
# • Termico do Compressor
# • Pressostato de Alta
# • Pressostato de Baixa
# • Pressostato de Oleo
# • Fluxostato de Condensacao
# • Botao de Emergencia
#
# Retorna uma lista contendo todos os alarmes ativos.
# ==============================================================


class SegurancaController:
    """
    Controlador das protecoes da maquina.
    """

    # ==========================================================
    # VERIFICACAO DAS PROTECOES
    # ==========================================================

    def verificar(self, entradas):
        """
        Analisa todas as entradas de seguranca.

        Parametro:

            entradas
                Dicionario contendo todas as entradas digitais.

        Retorno:

            Lista com os alarmes encontrados.
        """

        alarmes = []

        # ------------------------------------------------------
        # PARTIDA REMOTA
        # ------------------------------------------------------

        if not entradas["DI_PartidaRemota"]:
            alarmes.append("Partida Remota")

        # ------------------------------------------------------
        # PROTECAO DE ENERGIA
        # ------------------------------------------------------

        if not entradas["DI_ProtecaoEnergia"]:
            alarmes.append("Protecao Energia")

        # ------------------------------------------------------
        # FALHA EVAPORADOR
        # ------------------------------------------------------

        if entradas["DI_FalhaEvaporador"]:
            alarmes.append("Falha Evaporador")

        # ------------------------------------------------------
        # FALHA CONDENSADOR
        # ------------------------------------------------------

        if entradas["DI_FalhaCondensador"]:
            alarmes.append("Falha Condensador")

        # ------------------------------------------------------
        # TERMICO DO COMPRESSOR
        # ------------------------------------------------------

        if entradas["DI_TermicoCompressor"]:
            alarmes.append("Termico Compressor")

        # ------------------------------------------------------
        # PRESSOSTATO DE ALTA
        # ------------------------------------------------------

        if entradas["DI_PressostatoAlta"]:
            alarmes.append("Pressostato Alta")

        # ------------------------------------------------------
        # PRESSOSTATO DE BAIXA
        # ------------------------------------------------------

        if entradas["DI_PressostatoBaixa"]:
            alarmes.append("Pressostato Baixa")

        # ------------------------------------------------------
        # PRESSOSTATO DE OLEO
        # ------------------------------------------------------

        if entradas["DI_PressostatoOleo"]:
            alarmes.append("Pressostato Oleo")

        # ------------------------------------------------------
        # FLUXOSTATO DE CONDENSAÇÃO
        # ------------------------------------------------------

        if entradas.get("DI_FluxostatoCondensacao", False):
            alarmes.append("Fluxostato Condensacao")

        # ------------------------------------------------------
        # EMERGENCIA
        # ------------------------------------------------------

        if entradas.get("DI_Emergencia", False):
            alarmes.append("Emergencia")

        return alarmes