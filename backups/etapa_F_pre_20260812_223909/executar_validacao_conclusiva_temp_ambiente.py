"""Teste físico automático de um único sinal; não contém escrita no iPro."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import serial

from leitor_ipro_tcp import LeitorIPRO_TCP
from simulador_ipro_rs485 import crc16_modbus
from validacao_temp_ambiente_core import resposta_controlada


PASSOS = (20.0, 10.0, 0.0, -10.0, -20.0)
ESPERA_S = 20


class ServidorRestrito:
    def __init__(self, evidencia) -> None:
        self.bruto = 0
        self.lock = threading.Lock()
        self.parar_evento = threading.Event()
        self.pronto = threading.Event()
        self.erro = None
        self.serial = None
        self.thread = threading.Thread(target=self.executar, daemon=True)
        self.evidencia = evidencia

    def iniciar(self) -> None:
        self.thread.start()
        if not self.pronto.wait(5):
            raise RuntimeError("COM8 não ficou pronta em 5 segundos")
        if self.erro:
            raise RuntimeError(self.erro)

    def definir(self, temperatura: float) -> int:
        bruto = round(temperatura * 10)
        with self.lock:
            self.bruto = bruto
        return bruto

    def parar(self) -> None:
        self.parar_evento.set()
        if self.serial:
            self.serial.close()
        self.thread.join(2)

    def executar(self) -> None:
        try:
            self.serial = serial.Serial("COM8", 9600, bytesize=8, parity="N",
                                        stopbits=2, timeout=0.05)
            self.pronto.set()
            buffer = bytearray()
            while not self.parar_evento.is_set():
                dados = self.serial.read(256)
                if dados:
                    buffer.extend(dados)
                while len(buffer) >= 8:
                    frame = bytes(buffer[:8])
                    if crc16_modbus(frame[:6]) != int.from_bytes(frame[6:8], "little"):
                        del buffer[0]
                        continue
                    del buffer[:8]
                    with self.lock:
                        bruto = self.bruto
                    resultado = resposta_controlada(frame, bruto)
                    if resultado is None:
                        continue
                    resposta, _ = resultado
                    time.sleep(0.005)
                    self.serial.write(resposta)
                    self.serial.flush()
                    self.evidencia("resposta_rs485", {
                        "slave": 1, "funcao": 4, "endereco": 10,
                        "quantidade": 6, "valor_bruto": bruto,
                        "valores": [bruto, 0, 0, 0, 0, 0],
                    })
        except Exception as erro:
            self.erro = repr(erro)
            self.pronto.set()


def ler_w1() -> dict:
    inicio = time.perf_counter()
    url = "http://192.168.0.250/cgi-bin/xjgetvar.cgi?name=W1"
    with urllib.request.urlopen(url, timeout=5) as resposta:
        objeto = json.loads(resposta.read().decode("utf-8"))
    valor = int(objeto["values"][0]["value"][0])
    return {"valor": valor, "tempo_ms": round((time.perf_counter()-inicio)*1000, 3)}


def snapshot(leitor: LeitorIPRO_TCP) -> dict:
    w1 = ler_w1()
    fc03 = leitor.ler(1, 3, 384, 1).para_dict()
    fc04 = leitor.ler(1, 4, 384, 1).para_dict()
    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        "w1_0": w1,
        "fc03_384": fc03,
        "fc04_384": fc04,
    }


def valor_leitura(item: dict) -> int | None:
    valores = item.get("valores_int16", [])
    return valores[0] if item.get("status") == "OK" and valores else None


def main() -> int:
    pasta = Path(__file__).with_name("evidencias_validacao_modbus")
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"conclusiva_temp_ambiente_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def evidenciar(evento: str, dados: dict) -> None:
        with arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps({"evento": evento,
                "registrado_em": datetime.now().astimezone().isoformat(), **dados},
                ensure_ascii=False) + "\n")

    evidenciar("sessao_iniciada", {
        "sinal": "Temperatura Ambiente / W1[0]", "passos_c": PASSOS,
        "rs485": "COM8/9600/8N2 Slave 1 FC04 END 10 QTD 6",
        "tcp": "192.168.0.250:502 Unit 1 FC03/FC04 END 384 QTD 1",
        "escrita_ipro": False, "matriz_automatica": False,
    })
    servidor = ServidorRestrito(evidenciar)
    leitor = LeitorIPRO_TCP(timeout=5)
    resultados = []
    try:
        servidor.iniciar()
        evidenciar("com8_ativa", {"status": "OK"})
        for indice, temperatura in enumerate(PASSOS, 1):
            antes = snapshot(leitor)
            bruto = servidor.definir(temperatura)
            aplicado_em = datetime.now().astimezone().isoformat()
            evidenciar("passo_aplicado", {"passo": indice,
                "valor_enviado_c": temperatura, "valor_bruto": bruto,
                "offset": 0, "outros_offsets": [0,0,0,0,0],
                "timestamp_aplicacao": aplicado_em, "estado_antes": antes,
                "espera_s": ESPERA_S})
            print(f"PASSO {indice}/5: {temperatura:+.1f} °C; aguardando {ESPERA_S}s", flush=True)
            time.sleep(ESPERA_S)
            depois = snapshot(leitor)
            linha = {
                "passo": indice, "valor_enviado_c": temperatura,
                "valor_bruto_enviado": bruto, "timestamp_aplicacao": aplicado_em,
                "antes": antes, "depois": depois,
                "diferencas": {
                    "w1_0": depois["w1_0"]["valor"] - antes["w1_0"]["valor"],
                    "fc03_384": (valor_leitura(depois["fc03_384"]) - valor_leitura(antes["fc03_384"]))
                        if None not in (valor_leitura(depois["fc03_384"]), valor_leitura(antes["fc03_384"])) else None,
                    "fc04_384": (valor_leitura(depois["fc04_384"]) - valor_leitura(antes["fc04_384"]))
                        if None not in (valor_leitura(depois["fc04_384"]), valor_leitura(antes["fc04_384"])) else None,
                },
            }
            resultados.append(linha)
            evidenciar("passo_concluido", linha)
            print(f"  W1={depois['w1_0']['valor']} FC03={valor_leitura(depois['fc03_384'])} FC04={valor_leitura(depois['fc04_384'])}", flush=True)
        acompanhou = all(
            r["depois"]["w1_0"]["valor"] == r["valor_bruto_enviado"]
            and valor_leitura(r["depois"]["fc03_384"]) == r["valor_bruto_enviado"]
            and valor_leitura(r["depois"]["fc04_384"]) == r["valor_bruto_enviado"]
            for r in resultados
        )
        classificacao = "CONFIRMADO POR TESTE DE BANCADA" if acompanhou else "NÃO CONFIRMADO"
        evidenciar("sessao_concluida", {"classificacao": classificacao,
            "resultados": resultados, "matriz_alterada": False,
            "escrita_ipro": False})
        print(f"CLASSIFICAÇÃO={classificacao}", flush=True)
        print(f"EVIDÊNCIA={arquivo}", flush=True)
        return 0
    except Exception as erro:
        evidenciar("erro_fatal", {"erro_tipo": type(erro).__name__, "erro": repr(erro)})
        print(f"ERRO={erro!r}\nEVIDÊNCIA={arquivo}", flush=True)
        return 2
    finally:
        servidor.parar()


if __name__ == "__main__":
    raise SystemExit(main())
