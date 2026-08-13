# Arquitetura Final - CNCold Industrial Diagnostics

## Fluxo de dados

`EQUIPAMENTO -> TRANSPORTE -> DRIVER -> NORMALIZAÇÃO -> QUALIDADE -> HISTÓRICO -> EVENTOS -> ANÁLISE -> DIAGNÓSTICO -> ANOMALIAS -> INTERFACE -> RELATÓRIOS`

## Limites

- `application.py`: composição única e caminhos relativos ao projeto.
- `settings.py`: configuração externa tipada e barreiras contra inicialização automática.
- `drivers/`: identidade, mapa, política e estado de transporte independentes da UI.
- domínio: telemetria, sessões, baseline, degelo, incidentes, diagnóstico, anomalias e saúde.
- repositórios: SQLite/JSONL append-only ou auditável.
- `ui.py`: apresentação; não contém implementação serial/Modbus nem fórmulas analíticas.

## Persistência

Os bancos são separados por responsabilidade. Consultas temporais possuem índices em
sessão/canal e limites configuráveis. Resultados derivados registram evidências por ID,
modelo/regra/versão, data e auditoria. Dados originais não são modificados.

## Segurança

Construir a aplicação não ativa transportes. Configuração rejeita conexão automática,
inicialização RS485 automática e qualquer whitelist iPro diferente de FC03/FC04.
Importação de mapa apenas prepara versão pendente; não a ativa.

## Débito controlado

`ui.py` continua grande por conter 22 construtores de páginas e seus adaptadores de
apresentação. A lógica de negócio já está isolada. Dividir widgets em módulos é uma
melhoria futura de baixo risco, recomendada somente com testes de interação Qt mais
amplos; não foi feita na finalização para evitar reescrita cosmética.
