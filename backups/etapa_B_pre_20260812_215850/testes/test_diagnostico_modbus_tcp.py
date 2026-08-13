import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diagnostico_modbus_tcp_leitura import montar_requisicao, validar_requisicao


class TesteDiagnosticoSomenteLeitura(unittest.TestCase):
    def test_monta_fc04_modbus_tcp(self):
        self.assertEqual(
            montar_requisicao(1, 1, 4, 10, 6).hex(),
            "0001000000060104000a0006",
        )

    def test_monta_fc03_modbus_tcp(self):
        self.assertEqual(
            montar_requisicao(2, 2, 3, 256, 1).hex(),
            "000200000006020301000001",
        )

    def test_bloqueia_todas_as_funcoes_de_escrita(self):
        for funcao in (5, 6, 15, 16):
            with self.assertRaises(ValueError):
                validar_requisicao(1, funcao, 0, 1)


if __name__ == "__main__":
    unittest.main()
