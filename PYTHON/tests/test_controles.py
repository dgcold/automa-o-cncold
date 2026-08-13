from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from controllers.temperatura import TemperaturaController
from controllers.seguranca import SegurancaController
from controllers.condensacao import CondensacaoController


def test_temperatura():
    controle = TemperaturaController(setpoint=-18, diferencial=2)
    assert controle.precisa_refrigerar(-15)
    assert controle.atingiu_setpoint(-18)


def test_seguranca_sem_falhas():
    entradas = {
        "DI_PartidaRemota": True,
        "DI_ProtecaoEnergia": True,
    }
    assert SegurancaController().verificar(entradas) == []


def test_histerese_fan2():
    controle = CondensacaoController(fan2_on=270, fan2_off=240)
    assert controle.segundo_ventilador(269) is False
    assert controle.segundo_ventilador(270) is True
    assert controle.segundo_ventilador(250) is True
    assert controle.segundo_ventilador(240) is False
