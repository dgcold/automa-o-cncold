import struct
import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from simulador_ipro_rs485 import crc16_modbus
from validacao_temp_ambiente_core import quadro_exato, resposta_controlada


def requisicao(slave=1, funcao=4, endereco=10, quantidade=6):
    corpo = bytes([slave, funcao]) + struct.pack(">HH", endereco, quantidade)
    return corpo + struct.pack("<H", crc16_modbus(corpo))


class TesteValidacaoFisica(unittest.TestCase):
    def test_responde_exclusivamente_ao_bloco_autorizado(self):
        frame = requisicao()
        self.assertTrue(quadro_exato(frame))
        resposta, valores = resposta_controlada(frame, -200)
        self.assertEqual(valores, [0xFF38, 0, 0, 0, 0, 0])
        self.assertEqual(resposta[:3], bytes([1, 4, 12]))
        self.assertEqual(crc16_modbus(resposta[:-2]), int.from_bytes(resposta[-2:], "little"))

    def test_ignora_outros_enderecos_quantidades_slaves_e_funcoes(self):
        proibidas = [
            requisicao(endereco=11), requisicao(quantidade=5),
            requisicao(slave=2), requisicao(funcao=3),
            requisicao(funcao=5), requisicao(funcao=6),
            requisicao(funcao=15), requisicao(funcao=16),
        ]
        self.assertTrue(all(resposta_controlada(frame, 0) is None for frame in proibidas))

    def test_rejeita_crc_invalido(self):
        frame = bytearray(requisicao())
        frame[-1] ^= 0xFF
        self.assertIsNone(resposta_controlada(bytes(frame), 0))

    def test_mantem_offsets_um_a_cinco_em_zero(self):
        for bruto in (200, 100, 0, -100, -200):
            _, valores = resposta_controlada(requisicao(), bruto)
            self.assertEqual(valores[0], bruto & 0xFFFF)
            self.assertEqual(valores[1:], [0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
