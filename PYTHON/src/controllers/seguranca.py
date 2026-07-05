class SegurancaController:

    def verificar(self, entradas):

        alarmes = []

        if not entradas["DI_PartidaRemota"]:
            alarmes.append("Partida Remota")

        if not entradas["DI_ProtecaoEnergia"]:
            alarmes.append("Protecao Energia")

        if entradas["DI_FalhaEvaporador"]:
            alarmes.append("Falha Evaporador")

        if entradas["DI_FalhaCondensador"]:
            alarmes.append("Falha Condensador")

        if entradas["DI_TermicoCompressor"]:
            alarmes.append("Termico Compressor")

        if entradas["DI_PressostatoAlta"]:
            alarmes.append("Pressostato Alta")

        if entradas["DI_PressostatoBaixa"]:
            alarmes.append("Pressostato Baixa")

        if entradas["DI_PressostatoOleo"]:
            alarmes.append("Pressostato Oleo")

        return alarmes