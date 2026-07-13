# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : main.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Ponto de entrada da aplicacao.
#
# Responsavel por:
#
# • Criar a maquina principal.
# • Inicializar todos os controladores.
# • Iniciar a simulacao da camara frigorifica.
#
# Fluxo:
#
# main()
#     ↓
# Machine()
#     ↓
# iniciar()
#     ↓
# Loop principal da maquina
# ==============================================================

from core.machine import Machine


def main():
    """
    Inicializa a aplicacao.
    """

    print("=" * 60)
    print("      CN500_LT_IPRO - CNCOLD AUTOMATION")
    print("      Sistema de Controle de Câmara Frigorífica")
    print("      Versão 1.0")
    print("=" * 60)

    maquina = Machine()

    maquina.iniciar()


if __name__ == "__main__":
    main()