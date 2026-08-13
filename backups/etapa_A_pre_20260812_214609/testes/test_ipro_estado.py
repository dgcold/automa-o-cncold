import unittest
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config_modbus
from config_modbus import interpretar_booleano, mesclar_configuracao
from estado_maquina import (
    calcular_estado_maquina,
    controles_simulador_habilitados,
    deve_usar_dados_reais,
)
from ipro_map import (
    ConfiguracaoCanalIPro,
    QUALIDADE_DESATUALIZADA,
    QUALIDADE_PROVISORIA,
    QUALIDADE_INVALIDA,
    QUALIDADE_SEM_DADOS,
    decodificar_int16,
)
from modbus_rs485 import (
    COMUNICACAO_DESCONECTADO,
    COMUNICACAO_OK,
    COMUNICACAO_PARCIAL,
    ModbusRS485,
)


@dataclass
class CanalFake:
    valor: float
    minimo: float = -50.0
    maximo: float = 100.0


class GeradorFake:
    MODOS = {1: "MÁQUINA PARADA", 2: "RESFRIAMENTO", 4: "FALHA"}

    def __init__(self):
        self.modo = 2
        self.numero_falha = 1
        self.camara = CanalFake(20.0, -40.0, 50.0)
        self.evaporador = CanalFake(15.0, -50.0, 60.0)
        self.alarme_temp_camara = False
        self.alarme_descarga = False
        self.alarme_succao = False
        self.alarme_temp_descarga = False
        self.alarmes_automaticos = []

    @property
    def nome_modo(self):
        return self.MODOS[self.modo]

    @property
    def nome_falha(self):
        return "TEMPERATURA CÂMARA ABERTA"


def canal(endereco, trocar=False, tipo="int16", unidade="°C?"):
    return ConfiguracaoCanalIPro(
        endereco, tipo, trocar, 1.0, 0.0, unidade, unidade,
        True, -20000.0 if tipo == "int16" else None,
        20000.0 if tipo == "int16" else None,
    )


def modbus_fake(valores):
    objeto = ModbusRS485.__new__(ModbusRS485)
    objeto.simulado = False
    objeto.ultimo_erro = ""
    objeto._ultimas_leituras_validas = {}
    objeto.desconectar = lambda: None
    objeto.conectar = lambda: True

    def ler(endereco, quantidade):
        valor = valores[endereco]
        if isinstance(valor, Exception):
            raise valor
        return [valor]

    objeto._ler_registros = ler
    return objeto


class TesteOrdemDeBytesPorCanal(unittest.TestCase):
    def test_valores_sem_troca(self):
        self.assertEqual(decodificar_int16(208, False), 208)
        self.assertEqual(decodificar_int16(227, False), 227)

    def test_valores_com_troca_individual(self):
        casos = {3840: 15, 11520: 45, 14080: 55, 17920: 70}
        mapa = {
            nome: canal(indice, trocar=True)
            for indice, nome in enumerate(casos)
        }
        valores = dict(enumerate(casos))
        objeto = modbus_fake(valores)
        with patch("modbus_rs485.IPRO_CANAIS", mapa):
            dados = objeto.ler_ipro()
        self.assertEqual(
            [dados[nome] for nome in mapa],
            [15.0, 45.0, 55.0, 70.0],
        )

    def test_pressao_provisoria_nao_e_convertida_para_psi(self):
        mapa = {"pressao_descarga_bar": canal(394, True, unidade="bar?")}
        objeto = modbus_fake({394: 11520})
        with patch("modbus_rs485.IPRO_CANAIS", mapa):
            dados = objeto.ler_ipro()
        leitura = dados["_leituras"]["pressao_descarga_bar"]
        self.assertEqual(leitura["valor_escalado"], 45.0)
        self.assertEqual(leitura["valor_convertido"], 45.0)
        self.assertEqual(leitura["unidade_interface"], "bar?")
        self.assertNotIn("pressao_descarga_psi", dados)


class TesteQualidadeComunicacao(unittest.TestCase):
    def test_comunicacao_parcial_preserva_variavel_valida(self):
        mapa = {"a": canal(1), "b": canal(2)}
        objeto = modbus_fake({1: 10, 2: RuntimeError("falha")})
        with patch("modbus_rs485.IPRO_CANAIS", mapa):
            dados = objeto.ler_ipro()
        self.assertEqual(dados["_comunicacao"], COMUNICACAO_PARCIAL)
        self.assertEqual(dados["a"], 10.0)
        self.assertEqual(dados["_leituras"]["a"]["qualidade"], QUALIDADE_PROVISORIA)
        self.assertEqual(dados["_leituras"]["b"]["qualidade"], QUALIDADE_SEM_DADOS)

    def test_perda_total_cache_e_reconexao(self):
        mapa = {"a": canal(1)}
        valores = {1: 10}
        objeto = modbus_fake(valores)
        with patch("modbus_rs485.IPRO_CANAIS", mapa):
            primeira = objeto.ler_ipro()
            valores[1] = RuntimeError("desconectado")
            segunda = objeto.ler_ipro()
            valores[1] = 20
            terceira = objeto.ler_ipro()
        self.assertEqual(primeira["_comunicacao"], COMUNICACAO_OK)
        self.assertEqual(segunda["_comunicacao"], COMUNICACAO_DESCONECTADO)
        self.assertEqual(segunda["a"], 10.0)
        self.assertEqual(segunda["_leituras"]["a"]["qualidade"], QUALIDADE_DESATUALIZADA)
        self.assertEqual(terceira["_comunicacao"], COMUNICACAO_OK)
        self.assertEqual(terceira["a"], 20.0)

    def test_recarregar_configuracao_preserva_cache(self):
        objeto = modbus_fake({})
        objeto._ultimas_leituras_validas["a"] = {"valor": 10.0}
        config = {
            "porta": "COM9", "baudrate": 19200, "slave": 2,
            "paridade": "N", "stopbits": 1, "modo": "REAL",
        }
        with patch("modbus_rs485.carregar", return_value=config):
            objeto.recarregar_configuracao()
        self.assertEqual(objeto._ultimas_leituras_validas["a"]["valor"], 10.0)
        self.assertEqual(objeto.porta, "COM9")

    def test_implausivel_preserva_diagnostico_sem_substituir_cache(self):
        config = ConfiguracaoCanalIPro(
            1, "int16", False, 1.0, 0.0, "°C", "°C",
            False, -50.0, 100.0,
        )
        valores = {1: 20}
        objeto = modbus_fake(valores)
        with patch("modbus_rs485.IPRO_CANAIS", {"temperatura": config}):
            objeto.ler_ipro()
            valores[1] = 500
            dados = objeto.ler_ipro()
        leitura = dados["_leituras"]["temperatura"]
        self.assertEqual(leitura["valor_convertido"], 500.0)
        self.assertEqual(leitura["qualidade"], QUALIDADE_INVALIDA)
        self.assertEqual(leitura["ultimo_valor_valido"], 20.0)


class TesteEstadoEConfiguracao(unittest.TestCase):
    def test_controles_so_ficam_ativos_no_simulado(self):
        self.assertTrue(controles_simulador_habilitados("SIMULADO"))
        self.assertFalse(controles_simulador_habilitados("REAL"))
        self.assertFalse(controles_simulador_habilitados("AUTO"))

    def test_metodos_de_calculo_nao_usam_nomes_de_envio(self):
        self.assertTrue(hasattr(ModbusRS485, "calcular_canal_localmente"))
        self.assertTrue(hasattr(ModbusRS485, "calcular_todos_localmente"))
        self.assertFalse(hasattr(ModbusRS485, "enviar_canal"))
        self.assertFalse(hasattr(ModbusRS485, "enviar_todos"))

    def test_real_e_auto_nao_voltam_ao_simulador(self):
        self.assertTrue(deve_usar_dados_reais("REAL", False))
        self.assertFalse(deve_usar_dados_reais("AUTO", False))
        self.assertTrue(deve_usar_dados_reais("AUTO", True))

    def test_estado_parcial_e_desconectado(self):
        parcial = calcular_estado_maquina(
            GeradorFake(), modo_real=True, comunicacao=COMUNICACAO_PARCIAL,
            compressor=True, degelo=False,
        )
        perdido = calcular_estado_maquina(
            GeradorFake(), modo_real=True, comunicacao=COMUNICACAO_DESCONECTADO,
            compressor=True, degelo=False,
        )
        self.assertIn("PARCIAL", parcial.nome_modo)
        self.assertEqual(parcial.estado_compressor, "COMUNICAÇÃO PARCIAL")
        self.assertEqual(perdido.estado_compressor, "SEM COMUNICAÇÃO")

    def test_booleanos_de_json(self):
        verdadeiros = [True, 1, "true", "TRUE", "sim", "on"]
        falsos = [False, 0, "false", "FALSE", "não", "off", ""]
        self.assertTrue(all(interpretar_booleano(v) for v in verdadeiros))
        self.assertTrue(all(not interpretar_booleano(v, True) for v in falsos))

    def test_mescla_preserva_configuracoes_avancadas(self):
        atual = {"porta": "COM8", "mapa_canais": {"a": {"escala": 0.1}}}
        salvo = mesclar_configuracao(atual, {"porta": "COM9"})
        self.assertEqual(salvo["porta"], "COM9")
        self.assertEqual(salvo["mapa_canais"]["a"]["escala"], 0.1)

    def test_salvamento_json_preserva_configuracao_de_canal(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "config.json"
            config = mesclar_configuracao(
                config_modbus.CONFIG_PADRAO,
                {
                    "porta": "COM9",
                    "canais_ipro": {
                        "temperatura_camara": {
                            "endereco": 384,
                            "tipo": "int16",
                            "trocar_bytes": False,
                            "escala": 0.1,
                            "offset": 0.0,
                            "unidade": "°C",
                            "unidade_interface": "°C",
                            "provisoria": True,
                        }
                    },
                },
            )
            with patch.object(config_modbus, "ARQUIVO", arquivo):
                config_modbus.salvar(config)
                carregada = config_modbus.carregar()
        canal_salvo = carregada["canais_ipro"]["temperatura_camara"]
        self.assertFalse(canal_salvo["trocar_bytes"])
        self.assertEqual(canal_salvo["escala"], 0.1)


if __name__ == "__main__":
    unittest.main()
