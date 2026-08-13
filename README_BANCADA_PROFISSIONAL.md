# CNCold Industrial Diagnostics 1.0

Plataforma offline-first para bancada, diagnóstico de campo e análise explicável de
controladores de refrigeração. As Etapas A-I estão consolidadas; equipamentos reais e
mapas oficiais permanecem pendentes.

## Segurança

- O programa inicia em `SIMULADOR` e não abre rede ou serial.
- `REAL` é exclusivamente `SOMENTE LEITURA`.
- iPro real aceita apenas FC03/FC04; FC05/06/15/16 são bloqueadas.
- COM8 e Modbus TCP exigem ação explícita. Nenhum reset, STOP ou escrita existe.
- Aplicação v107, históricos, evidências e mapas existentes não são alterados.
- Candidatos nunca são promovidos automaticamente a mapa oficial.
- Ausência é exibida como `NÃO CONECTADO`, `SEM DADOS` ou `NÃO DETERMINADO`.

## Instalação e execução

Requisitos: Python 3.12+ e PySide6. O projeto não instala dependências ao iniciar.

```powershell
python -m pip install PySide6 pyserial pytest
python bench_main.py
```

Testes e compilação:

```powershell
python -m pytest -q
python -m compileall -q ipro_bench testes bench_main.py
```

Configuração central: `config/application.json`. Mapas e regras permanecem em arquivos
externos sob `config/`; não altere estados oficiais sem revisão rastreável.

## Arquitetura

```text
INTERFACE
  -> APLICAÇÃO / COMPOSIÇÃO
  -> DOMÍNIO E ANÁLISE
  -> TELEMETRIA NORMALIZADA / QUALIDADE
  -> DRIVERS
  -> TRANSPORTE EXPLÍCITO
  -> EQUIPAMENTO
```

`ipro_bench/application.py` cria os serviços e repositórios. A UI não implementa
Modbus, serial, baseline, análise, persistência ou diagnóstico; apenas chama serviços.

Principais módulos:

- `telemetry.py`, `history_store.py`, `evidence.py`: dados, qualidade e persistência.
- `field_diagnostics.py`: Caixa-Preta e Timeline.
- `baseline.py`, `defrost_analysis.py`, `incident_analysis.py`: análise operacional.
- `explainable_diagnostics.py`: hipóteses rastreáveis e auditoria.
- `anomaly_analysis.py`: distância estatística e abstinência.
- `operational_health.py`: saúde dimensional, tendências e assinaturas.
- `drivers/`: iPro, VX-1050E e dois EM210 offline.
- `ui.py`: apresentação e interação explícita do operador.

## Drivers e mapas

- iPro: driver somente leitura; mapa oficial vazio; candidatos separados.
- VX-1050E: driver offline; transporte e mapa aguardam documentação oficial.
- EM210 total e compressor: drivers offline independentes; mapas oficiais vazios.

Grandezas EM210 só serão adicionadas após confirmação oficial. Grandeza inexistente é
`NÃO DISPONÍVEL`; instrumento desligado é `NÃO CONECTADO / SEM DADOS`.

## Diagnóstico e análise

Categorias não são equivalentes:

```text
OBSERVADO -> INDICAÇÃO -> HIPÓTESE -> EVIDÊNCIA SUFICIENTE -> CONFIRMADO
```

Correlação não é causalidade. Anomalia não é diagnóstico. Score de saúde/anomalia não
é probabilidade de falha. Confirmação exige evidência e ação humana explícitas.

O catálogo `config/diagnostic_rules.json` permanece vazio até validação técnica.

## Dados, relatórios e diretórios

- `dados/`: SQLite de histórico, Caixa-Preta, baseline, diagnósticos, anomalias e saúde.
- `evidencias/`: JSONL append-only por categoria.
- `relatorios/`: PDF, CSV, JSON e bundles de sessão.
- `backups/`: backups versionados e manifestos SHA-256.
- `config/controllers/`: identidade, política e mapas oficiais de cada equipamento.
- `testes/`: regressão automatizada completa.

Não apague ou edite bancos/evidências manualmente. Use exportações para intercâmbio.

## Estado pendente

- iPro: aguardando mapa Modbus oficial.
- VX-1050E: aguardando mapa Modbus oficial.
- EM210 total/compressores: aguardando driver/mapa oficial.
- Regras diagnósticas: aguardando validação técnica.

Nenhum teste físico foi executado durante o desenvolvimento A-J.
