import csv
from datetime import datetime
from pathlib import Path


class Historico:
    def __init__(self):
        self.caminho = Path("dados_simulacao.csv")

        if not self.caminho.exists():
            with self.caminho.open(
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as arquivo:
                escritor = csv.writer(
                    arquivo,
                    delimiter=";",
                )

                escritor.writerow([
                    "Data",
                    "Hora",
                    "Estado",
                    "Compressor",
                    "Degelo",
                    "Agressividade (%)",
                    "Modo",
                    "Temperatura Câmara (°C)",
                    "Temperatura Evaporador (°C)",
                    "Pressão Sucção (PSI)",
                    "Pressão Descarga (PSI)",
                    "Pressão Óleo (PSI)",
                    "Diferencial Óleo (PSI)",
                ])

    def salvar(self, maquina):
        agora = datetime.now()

        if maquina.degelo_ligado:
            estado = "DEGELO"

        elif maquina.compressor_ligado:
            estado = "RESFRIANDO"

        else:
            estado = "PARADO"

        if maquina.agressividade <= 20:
            modo = "ESTÁVEL"

        elif maquina.agressividade <= 50:
            modo = "NORMAL"

        elif maquina.agressividade <= 80:
            modo = "INSTÁVEL"

        else:
            modo = "AGRESSIVO"

        diferencial_oleo = (
            maquina.pressao_oleo
            - maquina.pressao_succao
        )

        with self.caminho.open(
            "a",
            newline="",
            encoding="utf-8-sig",
        ) as arquivo:
            escritor = csv.writer(
                arquivo,
                delimiter=";",
            )

            escritor.writerow([
                agora.strftime("%d/%m/%Y"),
                agora.strftime("%H:%M:%S"),
                estado,
                (
                    "LIGADO"
                    if maquina.compressor_ligado
                    else "DESLIGADO"
                ),
                (
                    "LIGADO"
                    if maquina.degelo_ligado
                    else "DESLIGADO"
                ),
                maquina.agressividade,
                modo,
                f"{maquina.temperatura_camara:.2f}".replace(".", ","),
                f"{maquina.temperatura_evaporador:.2f}".replace(".", ","),
                f"{maquina.pressao_succao:.2f}".replace(".", ","),
                f"{maquina.pressao_descarga:.2f}".replace(".", ","),
                f"{maquina.pressao_oleo:.2f}".replace(".", ","),
                f"{diferencial_oleo:.2f}".replace(".", ","),
            ])