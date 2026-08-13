import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulador_ipro_rs485 import (
    EstadoSimulador, comparar_capturas, crc16_modbus, montar_resposta,
)


class TesteSimuladorIPro(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoSimulador({
            "blocos_confirmados": {
                "1": {"funcao": 4, "enderecos_iniciais": [10]},
                "2": {"funcao": 3, "enderecos_iniciais": [256]},
            },
            "valores_iniciais": {"1": {"10": -150}, "2": {"256": 100}},
            "sinais": {},
        })

    def test_crc_frame_confirmado(self):
        self.assertEqual(crc16_modbus(bytes.fromhex("0104000A0001")), 0xC811)

    def test_slave_1_responde_fc04_com_int16_negativo(self):
        resposta, valores = montar_resposta(self.estado, 1, 4, 10, 1)
        self.assertEqual(valores, [0xFF6A])
        self.assertEqual(resposta[:5], bytes.fromhex("010402FF6A"))
        self.assertEqual(int.from_bytes(resposta[-2:], "little"), crc16_modbus(resposta[:-2]))

    def test_slave_2_responde_fc03(self):
        resposta, valores = montar_resposta(self.estado, 2, 3, 256, 1)
        self.assertEqual(valores, [100])
        self.assertEqual(resposta[:5], bytes.fromhex("0203020064"))

    def test_funcao_incorreta_retorna_excecao_modbus(self):
        resposta, valores = montar_resposta(self.estado, 1, 3, 10, 1)
        self.assertEqual(valores, [])
        self.assertEqual(resposta[:3], bytes([1, 0x83, 1]))

    def test_compara_cada_posicao_do_bloco(self):
        estado_a = {(1, 4, 10): [200, 0, 30]}
        estado_b = {(1, 4, 10): [0xFED4, 0, 31]}
        linhas = comparar_capturas(estado_a, estado_b)
        self.assertEqual([linha["endereco"] for linha in linhas], [10, 11, 12])
        self.assertEqual(linhas[0]["estado_a"], 200)
        self.assertEqual(linhas[0]["estado_b"], -300)
        self.assertEqual(linhas[0]["delta"], -500)
        self.assertTrue(linhas[0]["mudou"])
        self.assertFalse(linhas[1]["mudou"])


if __name__ == "__main__":
    unittest.main()
