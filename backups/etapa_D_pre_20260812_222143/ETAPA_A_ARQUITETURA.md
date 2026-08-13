# ETAPA A - Arquitetura e limites

## Fluxo obrigatório

`EQUIPAMENTO -> DRIVER -> NORMALIZAÇÃO -> QUALIDADE -> HISTÓRICO -> EVENTOS -> ANÁLISE -> DIAGNÓSTICO -> IA -> INTERFACE -> RELATÓRIOS`

## Implementação

- **Equipamento/driver:** `TcpReadOnlyService` mantém o iPro real restrito a FC03/FC04. `ElectricalMeasurementService` é uma fronteira neutra preparada para receber, no futuro, dados de um driver EM210; não abre hardware.
- **Normalização/qualidade:** `TelemetrySample` impede valor em fonte desconectada e impede valor marcado como `SEM DADOS`.
- **Histórico:** `PersistentHistory` grava amostras append-only em SQLite, com consulta cronológica e média/mínimo/máximo.
- **Eventos:** `EvidenceStore` mantém JSONL append-only por categoria.
- **Análise/diagnóstico:** estatísticas são derivadas apenas de amostras reais recebidas; ausência de amostras permanece explícita.
- **Interface:** Sensores, I/O, Medição Elétrica, Cenários, Test Manager, Gráficos, Histórico e Relatórios são módulos separados. A interface legada continua disponível e não foi alterada.
- **Relatórios:** exportação local em PDF, CSV e JSON.

## Barreiras preservadas

- Modo REAL é somente leitura.
- Apenas FC03 e FC04 são aceitas no iPro real.
- COM8 nunca é aberta automaticamente.
- Nenhum teste físico é executado.
- iPro e VX-1050E permanecem `AGUARDANDO MAPA OFICIAL`.
- Endereços candidatos não são promovidos nem apresentados como oficiais.
- Sem driver/dados, a interface mostra `NÃO CONECTADO` e `SEM DADOS`.
