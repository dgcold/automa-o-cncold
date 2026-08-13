from __future__ import annotations

import struct
import threading
import time
from typing import Iterable

from config_modbus import carregar, interpretar_booleano
from conversao_sinais import calcular_saida_canal
from ipro_map import (
    IPRO_CANAIS,
    QUALIDADE_DESATUALIZADA,
    QUALIDADE_INVALIDA,
    QUALIDADE_PROVISORIA,
    QUALIDADE_SEM_DADOS,
    QUALIDADE_VALIDA,
    aplicar_escala,
    configurar_canais,
    decodificar_int16,
)

COMUNICACAO_OK = "OK"
COMUNICACAO_PARCIAL = "PARCIAL"
COMUNICACAO_DESCONECTADO = "DESCONECTADO"


class ModbusRS485:
    """Cliente Modbus RTU robusto para comunicação com o Copeland iPro."""

    def __init__(
        self,
        porta=None,
        baudrate=None,
        slave_id=None,
        simulado=None,
    ) -> None:
        config = carregar()

        self._aplicar_configuracao(config, porta, baudrate, slave_id, simulado)

        self.conectado = False
        self.ultimo_erro = ""
        self._cliente = None
        self._lock = threading.RLock()
        self._ultimas_leituras_validas: dict[str, dict[str, object]] = {}

    def _aplicar_configuracao(
        self,
        config: dict[str, object],
        porta=None,
        baudrate=None,
        slave_id=None,
        simulado=None,
    ) -> None:
        self.porta = str(porta or config.get("porta", "COM3"))
        self.baudrate = int(
            baudrate if baudrate is not None else config.get("baudrate", 9600)
        )
        self.slave_id = int(
            slave_id if slave_id is not None else config.get("slave", 1)
        )
        self.paridade = str(config.get("paridade", "N")).upper()
        self.stopbits = int(config.get("stopbits", 1))
        self.timeout = float(config.get("timeout", 0.5))
        self.retries = int(config.get("retries", 1))
        self.tabela_registro = str(
            config.get("tabela_registro", "holding")
        ).lower()
        self.offset_endereco = int(config.get("offset_endereco", 0))
        self.ordem_palavras = str(
            config.get("ordem_palavras", "big")
        ).lower()
        self.ordem_bytes = str(
            config.get("ordem_bytes", "big")
        ).lower()

        modo = str(config.get("modo", "SIMULADO")).upper()
        self.simulado = (
            modo == "SIMULADO"
            if simulado is None
            else interpretar_booleano(simulado)
        )
        self.canais_ipro = configurar_canais(
            config.get("canais_ipro", {})
        )

    @property
    def modo(self) -> str:
        return "SIMULADO" if self.simulado else "REAL"

    def conectar(self) -> bool:
        """Abre a porta serial sem derrubar a aplicação em caso de erro."""
        with self._lock:
            self.ultimo_erro = ""

            if self.simulado:
                self.conectado = True
                return True

            if self.conectado and self._cliente is not None:
                return True

            try:
                from pymodbus.client import ModbusSerialClient

                parametros = {
                    "port": self.porta,
                    "baudrate": self.baudrate,
                    "parity": self.paridade,
                    "stopbits": self.stopbits,
                    "bytesize": 8,
                    "timeout": self.timeout,
                    "retries": self.retries,
                }

                try:
                    self._cliente = ModbusSerialClient(
                        **parametros,
                        handle_local_echo=True,
                    )
                except TypeError:
                    self._cliente = ModbusSerialClient(**parametros)

                self.conectado = bool(self._cliente.connect())

                if not self.conectado:
                    self.ultimo_erro = (
                        f"Não foi possível abrir a porta {self.porta}."
                    )
                    self._cliente = None

                return self.conectado

            except (ImportError, OSError, ValueError, TypeError) as erro:
                self.conectado = False
                self._cliente = None
                self.ultimo_erro = str(erro)
                return False

    def desconectar(self) -> None:
        """Fecha a porta serial com segurança."""
        with self._lock:
            cliente = self._cliente
            self._cliente = None
            self.conectado = False

            if cliente is not None:
                try:
                    cliente.close()
                except Exception:
                    pass

    def _executar_leitura(self, metodo, endereco: int, quantidade: int):
        """Compatibilidade entre versões diferentes do pymodbus."""
        ultimo_type_error = None

        for chave in ("device_id", "slave", "unit"):
            try:
                return metodo(
                    address=endereco,
                    count=quantidade,
                    **{chave: self.slave_id},
                )
            except TypeError as erro:
                ultimo_type_error = erro
                continue

        if ultimo_type_error is not None:
            raise ultimo_type_error

        raise RuntimeError(
            "A versão do pymodbus não aceitou o identificador do slave."
        )

    def _ler_registros(self, endereco: int, quantidade: int) -> list[int]:
        """Lê registradores com bloqueio e uma repetição curta."""
        with self._lock:
            if self.simulado:
                raise RuntimeError("Selecione o modo REAL para ler o iPro.")

            if not self.conectado or self._cliente is None:
                if not self.conectar():
                    raise RuntimeError(
                        self.ultimo_erro or "Modbus não conectado."
                    )

            cliente = self._cliente
            if cliente is None:
                raise RuntimeError("Cliente Modbus indisponível.")

            metodo = (
                cliente.read_input_registers
                if self.tabela_registro == "input"
                else cliente.read_holding_registers
            )

            endereco_real = int(endereco) + self.offset_endereco
            ultimo_erro = None

            for tentativa in range(2):
                try:
                    if tentativa > 0:
                        time.sleep(0.05)

                    resposta = self._executar_leitura(
                        metodo,
                        endereco_real,
                        quantidade,
                    )

                    if resposta is None:
                        raise RuntimeError(
                            f"Sem resposta no registrador {endereco_real}."
                        )

                    if hasattr(resposta, "isError") and resposta.isError():
                        raise RuntimeError(
                            f"Resposta Modbus de erro no registrador "
                            f"{endereco_real}: {resposta}"
                        )

                    valores = getattr(resposta, "registers", None)

                    if valores is None:
                        raise RuntimeError(
                            f"Resposta sem registradores em {endereco_real}."
                        )

                    if len(valores) < quantidade:
                        raise RuntimeError(
                            f"Resposta incompleta no registrador "
                            f"{endereco_real}: esperado {quantidade}, "
                            f"recebido {len(valores)}."
                        )

                    self.ultimo_erro = ""
                    return [
                        int(valor) & 0xFFFF
                        for valor in valores[:quantidade]
                    ]

                except Exception as erro:
                    ultimo_erro = erro
                    self.ultimo_erro = str(erro)

                    if tentativa == 1:
                        self.conectado = False

            raise RuntimeError(
                self.ultimo_erro
                or f"Falha lendo registrador {endereco_real}."
            ) from ultimo_erro

    def _ler_int16(self, endereco: int, trocar_bytes: bool = False) -> int:
        """Lê um registrador de 16 bits com sinal."""
        valor_bruto = self._ler_registros(endereco, 1)[0]
        return decodificar_int16(
            valor_bruto,
            trocar_bytes=trocar_bytes,
        )

    def _ler_float32(self, endereco: int) -> float:
        regs = self._ler_registros(endereco, 2)

        if self.ordem_palavras == "little":
            regs.reverse()

        partes = []

        for reg in regs:
            parte = reg.to_bytes(2, "big")

            if self.ordem_bytes == "little":
                parte = parte[::-1]

            partes.append(parte)

        return float(struct.unpack(">f", b"".join(partes))[0])

    def _ler_bool(self, endereco: int) -> bool:
        return bool(self._ler_registros(endereco, 1)[0])

    def ler_ipro(self) -> dict[str, object]:
        """Lê o mapa do iPro sem interromper tudo se um endereço falhar."""
        if self.simulado:
            raise RuntimeError("Selecione o modo REAL para ler o iPro.")

        dados: dict[str, object] = {}
        leituras: dict[str, dict[str, object]] = {}
        erros: list[str] = []
        sucessos = 0

        canais_ipro = getattr(self, "canais_ipro", IPRO_CANAIS)
        for nome, canal in canais_ipro.items():
            try:
                bruto = self._ler_registros(canal.endereco, 1)[0]
                if canal.tipo == "bool":
                    ordenado = int(bruto)
                    escalado = bool(ordenado)
                    convertido = escalado
                    plausivel = ordenado in (0, 1)
                elif canal.tipo == "int16":
                    ordenado = decodificar_int16(bruto, canal.trocar_bytes)
                    escalado = aplicar_escala(ordenado, canal.escala, canal.offset)
                    # Conversão de unidade somente após validação explícita.
                    convertido = escalado
                    plausivel = (
                        (canal.minimo_fisico is None or convertido >= canal.minimo_fisico)
                        and (canal.maximo_fisico is None or convertido <= canal.maximo_fisico)
                    )
                else:
                    raise ValueError(f"Tipo de canal não suportado: {canal.tipo}")

                qualidade = (
                    QUALIDADE_INVALIDA
                    if not plausivel
                    else QUALIDADE_PROVISORIA
                    if canal.provisoria
                    else QUALIDADE_VALIDA
                )
                anterior = self._ultimas_leituras_validas.get(nome)
                ultimo_valido = (
                    convertido
                    if plausivel
                    else anterior.get("valor") if anterior else None
                )
                leitura = {
                    "endereco": canal.endereco,
                    "tipo": canal.tipo,
                    "valor_bruto": int(bruto),
                    "valor_ordenado": ordenado,
                    "valor_escalado": escalado,
                    "valor_convertido": convertido,
                    "valor": convertido,
                    "unidade_origem": canal.unidade,
                    "unidade_interface": canal.unidade_interface,
                    "qualidade": qualidade,
                    "ultimo_valor_valido": ultimo_valido,
                    "provisoria": canal.provisoria,
                    "erro": "" if plausivel else "Valor fisicamente implausível",
                }
                if plausivel:
                    self._ultimas_leituras_validas[nome] = dict(leitura)
                leituras[nome] = leitura
                dados[nome] = convertido
                sucessos += 1
            except Exception as erro:
                anterior = self._ultimas_leituras_validas.get(nome)
                valor_anterior = anterior.get("valor") if anterior else None
                leituras[nome] = {
                    "endereco": canal.endereco,
                    "tipo": canal.tipo,
                    "valor_bruto": None,
                    "valor_ordenado": None,
                    "valor_escalado": None,
                    "valor_convertido": None,
                    "valor": valor_anterior,
                    "unidade_origem": canal.unidade,
                    "unidade_interface": canal.unidade_interface,
                    "qualidade": (
                        QUALIDADE_DESATUALIZADA if anterior else QUALIDADE_SEM_DADOS
                    ),
                    "ultimo_valor_valido": valor_anterior,
                    "provisoria": canal.provisoria,
                    "erro": str(erro),
                }
                dados[nome] = valor_anterior
                erros.append(f"{nome}@{canal.endereco}: {erro}")

                try:
                    self.desconectar()
                    self.conectar()
                except Exception:
                    pass

        total = len(canais_ipro)
        comunicacao = (
            COMUNICACAO_OK
            if sucessos == total
            else COMUNICACAO_DESCONECTADO
            if sucessos == 0
            else COMUNICACAO_PARCIAL
        )
        dados["_leituras"] = leituras
        dados["_erros_leitura"] = erros
        dados["_comunicacao"] = comunicacao

        if erros:
            self.ultimo_erro = " | ".join(erros[:3])
        else:
            self.ultimo_erro = ""

        return dados

    def calcular_canal_localmente(self, canal) -> bool:
        if not self.conectado:
            self.ultimo_erro = "Modbus não conectado."
            return False

        if not canal.habilitado:
            return True

        try:
            calcular_saida_canal(canal)
            return True
        except (TypeError, ValueError) as erro:
            self.ultimo_erro = str(erro)
            return False

    def calcular_todos_localmente(self, canais: Iterable) -> bool:
        return all(self.calcular_canal_localmente(canal) for canal in canais)

    def resumo(self) -> dict[str, object]:
        return {
            "porta": self.porta,
            "baudrate": self.baudrate,
            "slave_id": self.slave_id,
            "paridade": self.paridade,
            "stopbits": self.stopbits,
            "timeout": self.timeout,
            "retries": self.retries,
            "modo": self.modo,
            "conectado": self.conectado,
            "ultimo_erro": self.ultimo_erro,
        }

    def recarregar_configuracao(self) -> None:
        self.desconectar()
        self._aplicar_configuracao(carregar())


def main() -> None:
    modbus = ModbusRS485()

    if modbus.conectar():
        print(modbus.resumo())

        if not modbus.simulado:
            try:
                print(modbus.ler_ipro())
            except Exception as erro:
                print(f"Erro de leitura: {erro}")
    else:
        print(modbus.resumo())


if __name__ == "__main__":
    main()
