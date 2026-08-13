import msvcrt
import time

import configuracao as cfg

from historico import Historico
from maquina import MaquinaSimulada
from terminal import mostrar


def processar_comando(maquina, comando):
    comando = comando.upper()

    if comando == "L":
        maquina.ligar_compressor()

    elif comando == "D":
        maquina.desligar_compressor()

    elif comando == "G":
        maquina.alternar_degelo()

    elif comando == "+":
        maquina.aumentar_agressividade()

    elif comando == "-":
        maquina.diminuir_agressividade()

    elif comando == "Q":
        return False

    return True


def main():
    maquina = MaquinaSimulada()
    historico = Historico()

    executando = True
    ultimo_tempo = time.monotonic()
    ultimo_registro = time.monotonic()

    while executando:
        agora = time.monotonic()
        tempo_decorrido = agora - ultimo_tempo
        ultimo_tempo = agora

        if msvcrt.kbhit():
            tecla = msvcrt.getwch()

            executando = processar_comando(
                maquina,
                tecla,
            )

        if not executando:
            break

        maquina.atualizar(
            tempo_decorrido
        )

        if (
            agora - ultimo_registro
            >= cfg.INTERVALO_REGISTRO_HISTORICO
        ):
            historico.salvar(maquina)
            ultimo_registro = agora

        mostrar(maquina)

        time.sleep(
            cfg.INTERVALO_ATUALIZACAO
        )

    print("Simulação encerrada.")


if __name__ == "__main__":
    main()