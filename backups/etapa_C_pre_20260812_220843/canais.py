from dataclasses import dataclass


@dataclass
class Canal:
    numero: int
    nome: str
    unidade: str
    minimo: float
    maximo: float
    valor: float
    habilitado: bool
    endereco_modbus: int
    tipo_saida: str


CANAIS = [
    Canal(1, "Temperatura Câmara", "°C", -40.0, 50.0, 20.0, True, 0, "0-10V"),
    Canal(2, "Temperatura Evaporador", "°C", -50.0, 60.0, 15.0, True, 1, "0-10V"),
    Canal(3, "Pressão Sucção", "PSI", 0.0, 150.0, 90.0, True, 2, "4-20mA"),
    Canal(4, "Pressão Descarga", "PSI", 0.0, 500.0, 100.0, True, 3, "4-20mA"),
    Canal(5, "Temperatura Descarga", "°C", -20.0, 180.0, 30.0, True, 4, "0-10V"),
    Canal(6, "Temperatura Linha Sucção", "°C", -50.0, 80.0, 10.0, True, 5, "0-10V"),
    Canal(7, "Temperatura Linha Líquido", "°C", -20.0, 100.0, 35.0, True, 6, "0-10V"),
    Canal(8, "Reserva", "", 0.0, 100.0, 0.0, False, 7, "0-10V"),
]
