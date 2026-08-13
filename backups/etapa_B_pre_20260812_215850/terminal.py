import os


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")


def mostrar(maquina):
    limpar_tela()

    print("=" * 70)
    print("              CNCOLD DIGITAL TWIN")
    print("=" * 70)

    print(f"Compressor    : {'LIGADO' if maquina.compressor_ligado else 'DESLIGADO'}")
    print(f"Degelo        : {'LIGADO' if maquina.degelo_ligado else 'DESLIGADO'}")
    print(f"Agressividade : {maquina.agressividade}%")

    if maquina.compressor_ligado:
        estado = "RESFRIANDO"

    elif maquina.degelo_ligado:
        estado = "DEGELO"

    else:
        estado = "PARADO"

    print(f"Estado        : {estado}")

    print("-" * 70)

    print(f"Temperatura Câmara      : {maquina.temperatura_camara:8.2f} °C")
    print(f"Temperatura Evaporador  : {maquina.temperatura_evaporador:8.2f} °C")

    print()

    print(f"Pressão Sucção          : {maquina.pressao_succao:8.2f} PSI")
    print(f"Pressão Descarga        : {maquina.pressao_descarga:8.2f} PSI")
    print(f"Pressão Óleo            : {maquina.pressao_oleo:8.2f} PSI")
    print(f"Diferencial de Óleo     : {(maquina.pressao_oleo - maquina.pressao_succao):8.2f} PSI")

    print("-" * 70)

    print("COMANDOS")
    print(" L  -> Ligar Compressor")
    print(" D  -> Desligar Compressor")
    print(" G  -> Ligar/Desligar Degelo")
    print(" +  -> Aumentar Agressividade")
    print(" -  -> Diminuir Agressividade")
    print(" Q  -> Sair")

    print("=" * 70)