from __future__ import annotations

from typing import Callable

from leitor_ipro_tcp import LeitorIPRO_TCP
from simulador_ipro_rs485 import EstadoSimulador, ServidorRTU


class TcpReadOnlyService:
    """Fachada explícita somente leitura sobre o cliente existente."""

    def __init__(self, host: str = "192.168.0.250", port: int = 502, timeout: float = 2.0) -> None:
        self.client = LeitorIPRO_TCP(host, port, timeout)

    def test_connection(self) -> dict:
        return self.client.testar_conexao()

    def read(self, unit_id: int, function: int, address: int, quantity: int):
        if function not in (3, 4):
            raise PermissionError("A bancada permite somente FC03 e FC04 no iPro real.")
        return self.client.ler(unit_id, function, address, quantity)


class Rs485SimulatorService:
    """Integração sob demanda. Construir esta classe não abre a COM8."""

    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self.state = EstadoSimulador()
        self.server = ServidorRTU(self.state, log=logger)

    @property
    def active(self) -> bool:
        return self.server.ativo

    def start(self) -> None:
        self.server.iniciar()

    def stop(self) -> None:
        self.server.parar()
