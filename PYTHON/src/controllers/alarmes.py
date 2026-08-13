# -*- coding: utf-8 -*-

# ==============================================================
# PROJETO : CN500_LT_IPRO
# EMPRESA : CN Cold
#
# ARQUIVO : alarmes.py
#
# AUTOR   : Douglas Silva Florencio
# DATA    : Julho/2026
# VERSAO  : 1.0
#
# DESCRICAO
# --------------------------------------------------------------
# Responsavel pelo gerenciamento dos alarmes da maquina.
#
# Recursos:
#
# • Adicionar alarmes
# • Remover alarmes
# • Limpar alarmes
# • Consultar alarmes ativos
# • Listar todos os alarmes
#
# Este modulo centraliza todos os eventos de falha do sistema.
# ==============================================================


class AlarmesController:
    """
    Controlador de alarmes da maquina.
    """

    # ==========================================================
    # INICIALIZACAO
    # ==========================================================

    def __init__(self):
        """
        Inicializa a lista de alarmes.
        """

        self.alarmes = []

    # ==========================================================
    # ADICIONAR ALARME
    # ==========================================================

    def adicionar(self, mensagem):
        """
        Adiciona um novo alarme.

        Alarmes duplicados nao sao adicionados.
        """

        if mensagem not in self.alarmes:

            self.alarmes.append(mensagem)

            print(f"ALARME ATIVO: {mensagem}")

    # ==========================================================
    # REMOVER ALARME
    # ==========================================================

    def remover(self, mensagem):
        """
        Remove um alarme da lista.
        """

        if mensagem in self.alarmes:

            self.alarmes.remove(mensagem)

            print(f"ALARME REMOVIDO: {mensagem}")

    # ==========================================================
    # LIMPAR ALARMES
    # ==========================================================

    def limpar(self):
        """
        Remove todos os alarmes ativos.
        """

        self.alarmes.clear()

    # ==========================================================
    # EXISTE ALARME
    # ==========================================================

    def existe_alarme(self):
        """
        Verifica se existe algum alarme ativo.

        Retorno:

            True
                Existe pelo menos um alarme.

            False
                Nenhum alarme ativo.
        """

        return len(self.alarmes) > 0

    # ==========================================================
    # LISTAR ALARMES
    # ==========================================================

    def listar(self):
        """
        Retorna todos os alarmes ativos.
        """

        return self.alarmes.copy()

    # ==========================================================
    # QUANTIDADE DE ALARMES
    # ==========================================================

    def quantidade(self):
        """
        Retorna a quantidade de alarmes ativos.
        """

        return len(self.alarmes)

    # ==========================================================
    # STATUS
    # ==========================================================

    def status(self):
        """
        Retorna um resumo do estado dos alarmes.
        """

        return {
            "quantidade": len(self.alarmes),
            "alarmes": self.alarmes.copy(),
        }