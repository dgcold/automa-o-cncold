import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from validacao_temp_ambiente_core import LeitorIPRO_TCP


class TesteLeitorIPRO_TCP(unittest.TestCase):
    def test_configuracao_inicial(self):
        leitor = LeitorIPRO_TCP()
        self.assertEqual(leitor.host, "192.168.0.250")
        self.assertEqual(leitor.porta, 502)
        self.assertEqual(leitor.funcao, 4)
        self.assertEqual(leitor.unit_id, 1)
        self.assertEqual(leitor.endpoint, "tcp://192.168.0.250:502")

    def test_erro_conexao_recusada_informa_detalhes(self):
        with patch("validacao_temp_ambiente_core.socket.create_connection",
                   side_effect=ConnectionRefusedError("Connection refused")):
            with self.assertRaises(RuntimeError) as cm:
                LeitorIPRO_TCP().ler()
        mensagem = str(cm.exception)
        self.assertIn("endpoint=tcp://192.168.0.250:502", mensagem)
        self.assertIn("classificacao=conexao recusada", mensagem)

    def test_erro_timeout_informa_detalhes(self):
        with patch("validacao_temp_ambiente_core.socket.create_connection",
                   side_effect=socket.timeout("timed out")):
            with self.assertRaises(RuntimeError) as cm:
                LeitorIPRO_TCP().ler()
        mensagem = str(cm.exception)
        self.assertIn("classificacao=timeout", mensagem)
        self.assertIn("erro_original=timed out", mensagem)

    def test_erro_modbus_por_canal_retorna_estado_parcial(self):
        socket_mock = MagicMock()
        socket_mock.__enter__.return_value = socket_mock
        with patch("validacao_temp_ambiente_core.socket.create_connection",
                   return_value=socket_mock):
            leitor = LeitorIPRO_TCP()
            with patch.object(leitor, "_ler_registro",
                              side_effect=RuntimeError("Modbus TCP resposta inválida")):
                resultado = leitor.ler()
        self.assertEqual(resultado["_comunicacao"], "PARCIAL")
        self.assertTrue(resultado["_erros_leitura"])
        self.assertTrue(all("Modbus TCP resposta inválida" in erro
                            for erro in resultado["_erros_leitura"]))


if __name__ == "__main__":
    unittest.main()
