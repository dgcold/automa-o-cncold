from __future__ import annotations

import json
import struct
import threading
import time
from pathlib import Path
from typing import Callable


ARQUIVO_CONFIG = Path(__file__).with_name("config_simulador_ipro.json")


def crc16_modbus(dados: bytes) -> int:
    crc = 0xFFFF
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def carregar_configuracao() -> dict:
    with ARQUIVO_CONFIG.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_configuracao(config: dict) -> None:
    with ARQUIVO_CONFIG.open("w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, indent=2, ensure_ascii=False)
        arquivo.write("\n")


class EstadoSimulador:
    """Estado thread-safe. Associações físicas só existem após validação manual."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or carregar_configuracao()
        self._lock = threading.RLock()
        self.valores = {
            int(slave): {int(endereco): int(valor) for endereco, valor in regs.items()}
            for slave, regs in self.config["valores_iniciais"].items()
        }

    def funcao_esperada(self, slave: int) -> int | None:
        bloco = self.config["blocos_confirmados"].get(str(slave))
        return int(bloco["funcao"]) if bloco else None

    def ler(self, slave: int, endereco: int, quantidade: int) -> list[int]:
        with self._lock:
            regs = self.valores.get(slave, {})
            return [int(regs.get(endereco + i, 0)) & 0xFFFF for i in range(quantidade)]

    def definir_registro(self, slave: int, endereco: int, valor: int) -> None:
        with self._lock:
            self.valores.setdefault(int(slave), {})[int(endereco)] = int(valor)

    def associar_sinal(self, nome: str, slave: int | None, endereco: int | None,
                       escala: float = 10.0, offset: float = 0.0) -> None:
        sinal = self.config["sinais"][nome]
        sinal["associacao"] = None if slave is None else {
            "slave": int(slave), "endereco": int(endereco),
            "escala": float(escala), "offset": float(offset),
            "status": "DEFINIDA_PELO_USUARIO",
        }
        salvar_configuracao(self.config)
        self.definir_sinal(nome, float(sinal["valor"]))

    def definir_sinal(self, nome: str, valor: float) -> bool:
        sinal = self.config["sinais"][nome]
        sinal["valor"] = float(valor)
        associacao = sinal.get("associacao")
        if not associacao:
            return False
        bruto = round((float(valor) - associacao["offset"]) * associacao["escala"])
        self.definir_registro(associacao["slave"], associacao["endereco"], bruto)
        return True


def montar_resposta(estado: EstadoSimulador, slave: int, funcao: int,
                     endereco: int, quantidade: int) -> tuple[bytes, list[int]]:
    esperada = estado.funcao_esperada(slave)
    if esperada is None:
        raise ValueError("slave desconhecido")
    if funcao != esperada:
        corpo = bytes([slave, funcao | 0x80, 1])
        crc = crc16_modbus(corpo)
        return corpo + struct.pack("<H", crc), []
    if quantidade < 1 or quantidade > 125:
        corpo = bytes([slave, funcao | 0x80, 3])
        crc = crc16_modbus(corpo)
        return corpo + struct.pack("<H", crc), []
    valores = estado.ler(slave, endereco, quantidade)
    corpo = bytes([slave, funcao, quantidade * 2]) + b"".join(
        struct.pack(">H", valor) for valor in valores
    )
    return corpo + struct.pack("<H", crc16_modbus(corpo)), valores


def valor_com_sinal(valor: int) -> int:
    valor = int(valor) & 0xFFFF
    return valor - 0x10000 if valor >= 0x8000 else valor


def comparar_capturas(
    estado_a: dict[tuple[int, int, int], list[int]],
    estado_b: dict[tuple[int, int, int], list[int]],
) -> list[dict[str, int | bool | None]]:
    """Compara cada posição dos blocos, sem atribuir significado físico."""
    linhas = []
    for chave in sorted(set(estado_a) | set(estado_b)):
        slave, funcao, inicio = chave
        valores_a = estado_a.get(chave, [])
        valores_b = estado_b.get(chave, [])
        for posicao in range(max(len(valores_a), len(valores_b))):
            bruto_a = valores_a[posicao] if posicao < len(valores_a) else None
            bruto_b = valores_b[posicao] if posicao < len(valores_b) else None
            valor_a = valor_com_sinal(bruto_a) if bruto_a is not None else None
            valor_b = valor_com_sinal(bruto_b) if bruto_b is not None else None
            linhas.append({
                "slave": slave,
                "funcao": funcao,
                "inicio_bloco": inicio,
                "posicao": posicao,
                "endereco": inicio + posicao,
                "estado_a": valor_a,
                "estado_b": valor_b,
                "delta": (
                    valor_b - valor_a
                    if valor_a is not None and valor_b is not None
                    else None
                ),
                "mudou": valor_a != valor_b,
            })
    return linhas


class ServidorRTU:
    def __init__(self, estado: EstadoSimulador | None = None,
                 log: Callable[[str], None] | None = None,
                 ao_responder: Callable[[dict], None] | None = None) -> None:
        self.estado = estado or EstadoSimulador()
        self.log = log or (lambda mensagem: None)
        self.ao_responder = ao_responder or (lambda consulta: None)
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._serial = None
        self.ultimo_erro = ""

    @property
    def ativo(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def iniciar(self) -> None:
        if self.ativo:
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._executar, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        serial_atual = self._serial
        if serial_atual is not None:
            try:
                serial_atual.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _executar(self) -> None:
        config = self.estado.config
        try:
            import serial
            self._serial = serial.Serial(
                config["porta"], config["baudrate"], bytesize=config["bytesize"],
                parity=config["paridade"], stopbits=config["stopbits"],
                timeout=config["timeout"],
            )
            self.log(f"ATIVO {config['porta']} / {config['baudrate']} / 8N2")
            buffer = bytearray()
            while not self._parar.is_set():
                dados = self._serial.read(256)
                if dados:
                    buffer.extend(dados)
                while len(buffer) >= 8:
                    frame = bytes(buffer[:8])
                    if crc16_modbus(frame[:6]) != int.from_bytes(frame[6:8], "little"):
                        del buffer[0]
                        continue
                    del buffer[:8]
                    slave, funcao = frame[0], frame[1]
                    if self.estado.funcao_esperada(slave) is None:
                        continue
                    endereco = int.from_bytes(frame[2:4], "big")
                    quantidade = int.from_bytes(frame[4:6], "big")
                    resposta, valores = montar_resposta(
                        self.estado, slave, funcao, endereco, quantidade
                    )
                    time.sleep(float(config["atraso_resposta_s"]))
                    self._serial.write(resposta)
                    self._serial.flush()
                    exibicao = [valor_com_sinal(v) for v in valores]
                    self.log(f"ID={slave} FC={funcao:02d} END={endereco} QTD={quantidade} VAL={exibicao}")
                    try:
                        self.ao_responder({
                            "timestamp": time.time(),
                            "slave": slave,
                            "funcao": funcao,
                            "endereco": endereco,
                            "quantidade": quantidade,
                            "valores": list(valores),
                        })
                    except Exception as erro_callback:
                        self.log(f"ERRO NO REGISTRO DA CAPTURA: {erro_callback}")
        except Exception as erro:
            if not self._parar.is_set():
                self.ultimo_erro = str(erro)
                self.log(f"ERRO: {erro}")
        finally:
            self._serial = None


def executar_console() -> None:
    estado = EstadoSimulador()
    servidor = ServidorRTU(estado, print)
    print("iPro - simulador RS485 | COM8 / 9600 / 8N2")
    print("Slave 1: FC04 | Slave 2: FC03 | Ctrl+C para parar")
    print("Significados dos registradores: DESCONHECIDOS")
    servidor.iniciar()
    try:
        while servidor.ativo:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        servidor.parar()


if __name__ == "__main__":
    executar_console()
