"""Busca final controlada: varia somente inícios de blocos RTU já observados."""

from __future__ import annotations

import json, math, struct, threading, time, urllib.request
from datetime import datetime
from pathlib import Path

import serial

from simulador_ipro_rs485 import crc16_modbus

PASSOS = (200, 100, 0, -100, -200)
CANDIDATOS = ((10, 4, 14), (10, 5, 15))
BLOCOS = {10: 6, 20: 8, 34: 8, 42: 8, 50: 8, 58: 8,
          200: 8, 1200: 8, 1208: 8, 1216: 8}
ESPERA_S = 6


def ler_w1_0() -> tuple[int, str, float]:
    inicio = time.perf_counter()
    with urllib.request.urlopen(
        "http://192.168.0.250/cgi-bin/xjgetvar.cgi?name=W1", timeout=5
    ) as resposta:
        obj = json.loads(resposta.read().decode("utf-8"))
    return (int(obj["values"][0]["value"][0]),
            datetime.now().astimezone().isoformat(),
            round((time.perf_counter() - inicio) * 1000, 3))


class Servidor:
    def __init__(self, evidencia) -> None:
        self.alvo_bloco = None
        self.alvo_offset = None
        self.valor = 0
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.erro = None
        self.porta = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.evidencia = evidencia

    def iniciar(self):
        self.thread.start()
        if not self.ready.wait(5) or self.erro:
            raise RuntimeError(self.erro or "COM8 não abriu")

    def definir(self, bloco, offset, valor):
        with self.lock:
            self.alvo_bloco, self.alvo_offset, self.valor = bloco, offset, valor

    def parar(self):
        self.stop.set()
        if self.porta:
            self.porta.close()
        self.thread.join(2)

    def run(self):
        try:
            self.porta = serial.Serial("COM8", 9600, bytesize=8, parity="N",
                                       stopbits=2, timeout=0.05)
            self.ready.set()
            buffer = bytearray()
            while not self.stop.is_set():
                dados = self.porta.read(256)
                if dados: buffer.extend(dados)
                while len(buffer) >= 8:
                    frame = bytes(buffer[:8])
                    if crc16_modbus(frame[:6]) != int.from_bytes(frame[6:8], "little"):
                        del buffer[0]; continue
                    del buffer[:8]
                    slave, fc = frame[0], frame[1]
                    endereco = int.from_bytes(frame[2:4], "big")
                    qtd = int.from_bytes(frame[4:6], "big")
                    if slave != 1 or fc != 4 or BLOCOS.get(endereco) != qtd:
                        continue
                    with self.lock:
                        alvo, alvo_offset, valor = self.alvo_bloco, self.alvo_offset, self.valor
                    vals = [0] * qtd
                    if endereco == alvo and alvo_offset is not None:
                        vals[alvo_offset] = valor
                    corpo = bytes([1, 4, qtd * 2]) + b"".join(
                        struct.pack(">H", v & 0xFFFF) for v in vals)
                    resposta = corpo + struct.pack("<H", crc16_modbus(corpo))
                    time.sleep(0.005); self.porta.write(resposta); self.porta.flush()
                    if endereco == alvo:
                        self.evidencia("resposta_candidato", {
                            "slave": 1, "funcao": 4, "endereco": endereco,
                            "quantidade": qtd, "valores": vals})
        except Exception as erro:
            self.erro = repr(erro); self.ready.set()


def correlacao(xs, ys):
    if len(set(ys)) < 2: return 0.0
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    den = math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
    return round(num/den, 6) if den else 0.0


def main():
    pasta = Path(__file__).with_name("evidencias_validacao_modbus"); pasta.mkdir(exist_ok=True)
    arq = pasta / f"busca_final_w1_0_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    def ev(evento, dados):
        with arq.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"evento":evento,"registrado_em":datetime.now().astimezone().isoformat(),**dados},ensure_ascii=False)+"\n")
    ev("sessao_iniciada", {"candidatos":CANDIDATOS,"passos_brutos":PASSOS,
       "espera_s":ESPERA_S,"escrita_ipro":False,"matriz_automatica":False})
    servidor=Servidor(ev); servidor.iniciar(); resultados=[]
    try:
        for bloco, offset, endereco in CANDIDATOS:
            passos=[]
            for bruto in PASSOS:
                antes, ta, la = ler_w1_0()
                servidor.definir(bloco, offset, bruto)
                aplicado=datetime.now().astimezone().isoformat()
                time.sleep(ESPERA_S)
                depois, td, ld = ler_w1_0()
                linha={"slave":1,"funcao":4,"endereco":endereco,
                    "bloco":bloco,"offset":offset,"valor_enviado":bruto,"temperatura_c":bruto/10,
                    "w1_0_antes":antes,"w1_0_depois":depois,
                    "diferenca":depois-antes,"timestamp_antes":ta,
                    "timestamp_aplicacao":aplicado,"timestamp_depois":td,
                    "latencia_w1_antes_ms":la,"latencia_w1_depois_ms":ld}
                passos.append(linha); ev("passo",linha)
                print(f"END={endereco} ENV={bruto} W1={antes}->{depois}",flush=True)
            ys=[p["w1_0_depois"] for p in passos]
            score=correlacao(list(PASSOS),ys)
            exatos=sum(y==x for x,y in zip(PASSOS,ys))
            mudancas=sum(p["diferenca"]!=0 for p in passos)
            resumo={"slave":1,"funcao":4,"endereco":endereco,
                "correlacao":score,"acertos_exatos":exatos,
                "passos_com_mudanca":mudancas,
                "classificacao":"CANDIDATO" if abs(score)>=0.8 and mudancas>=3 else "NÃO CONFIRMADO",
                "passos":passos}
            resultados.append(resumo); ev("candidato_concluido",resumo)
        ranking=sorted(resultados,key=lambda r:(-abs(r["correlacao"]),-r["acertos_exatos"],-r["passos_com_mudanca"],r["endereco"]))
        ev("sessao_concluida",{"top5":ranking[:5],"todos":ranking,
            "matriz_alterada":False,"escrita_ipro":False})
        print("TOP5="+json.dumps(ranking[:5],ensure_ascii=False),flush=True)
        print(f"EVIDÊNCIA={arq}",flush=True)
        return 0
    finally:
        servidor.parar()

if __name__=="__main__": raise SystemExit(main())
