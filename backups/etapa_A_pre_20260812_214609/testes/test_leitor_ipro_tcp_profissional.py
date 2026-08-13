import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from correlacao_ipro_tcp import comparar_snapshots
from leitor_ipro_tcp import LeitorIPRO_TCP


class TesteLeitorProfissional(unittest.TestCase):
    def test_bloqueia_escritas(self):
        for fc in (5, 6, 15, 16):
            with self.assertRaises(PermissionError):
                LeitorIPRO_TCP.validar_leitura(1, fc, 0, 1)

    def test_permite_apenas_fc03_fc04(self):
        for fc in (3, 4):
            LeitorIPRO_TCP.validar_leitura(1, fc, 0, 1)
        with self.assertRaises(PermissionError):
            LeitorIPRO_TCP.validar_leitura(1, 1, 0, 1)

    def test_decodifica_resposta_fc04(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        resposta = struct.pack(">HHHB", 1, 0, 5, 1) + bytes([4, 2, 0xFF, 0x9C])
        sock.recv.side_effect = [resposta[:7], resposta[7:]]
        with patch("leitor_ipro_tcp.socket.create_connection", return_value=sock):
            leitura = LeitorIPRO_TCP().ler(1, 4, 10, 1)
        self.assertEqual(leitura.status, "OK")
        self.assertEqual(leitura.valores_uint16, [65436])
        self.assertEqual(leitura.valores_int16, [-100])

    def test_excecao_modbus_preservada(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        resposta = struct.pack(">HHHB", 1, 0, 3, 1) + bytes([0x84, 2])
        sock.recv.side_effect = [resposta[:7], resposta[7:]]
        with patch("leitor_ipro_tcp.socket.create_connection", return_value=sock):
            leitura = LeitorIPRO_TCP().ler(1, 4, 0, 1)
        self.assertEqual(leitura.status, "EXCECAO_MODBUS")
        self.assertEqual(leitura.codigo_excecao, 2)

    def test_comparacao_somente_cria_candidato(self):
        base = {"nome": "ANTES", "leituras": [{"unit_id": 1, "funcao": 4,
            "endereco": 0, "valores_int16": [100]}]}
        novo = {"nome": "DEPOIS", "leituras": [{"unit_id": 1, "funcao": 4,
            "endereco": 0, "valores_int16": [200]}]}
        resultado = comparar_snapshots(base, novo)
        self.assertFalse(resultado["classificacao_automatica"])
        self.assertEqual(resultado["alteracoes"][0]["classificacao"], "CANDIDATO")


if __name__ == "__main__":
    unittest.main()
