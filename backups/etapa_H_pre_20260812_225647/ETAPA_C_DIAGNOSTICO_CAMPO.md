# ETAPA C - Diagnóstico de Campo, Caixa-Preta e Timeline

## Fluxo reutilizável

`DRIVERS -> VARIÁVEIS NORMALIZADAS -> CAIXA-PRETA -> TIMELINE -> ANÁLISE -> EVIDÊNCIAS -> RELATÓRIO`

`BlackBoxRecorder` não consulta equipamentos. Ele recebe somente `TelemetrySample`
de uma fonte externa e pode, portanto, ser alimentado futuramente pelos drivers iPro,
VX-1050E e EM210 sem reconstrução da Timeline.

## Registro

- Sessões persistentes SQLite com início/fim e bloqueio após finalização.
- Timestamp ISO com microssegundos e contador Unix em nanossegundos.
- Amostras, mudanças de valor/estado, qualidade, alarmes, comunicação e marcadores.
- Evidência JSON associada a cada registro.
- Nenhuma interpolação ou preenchimento de lacunas.

## Timeline e análise

- Filtros por variável, tipo de evento e janela temporal.
- Cursor em `timestamp_ns` e zoom por intervalo.
- Identificação do primeiro desvio registrado.
- Contexto antes/depois e cálculo de duração.
- Correlação de séries numéricas existentes.
- Registro explícito de recuperação; ausência significa `NÃO DETERMINADO`.

## Exportação

- Bundle ZIP contendo `session.json` e `timeline.csv`.
- Relatório PDF resumindo registros, primeiro desvio, recuperação e evidências.

## Segurança

- Operação inicial integralmente offline.
- Nenhuma abertura de COM8 ou Modbus TCP.
- Nenhum valor sintético inserido automaticamente.
- Mapas oficiais continuam pendentes e candidatos continuam separados.
