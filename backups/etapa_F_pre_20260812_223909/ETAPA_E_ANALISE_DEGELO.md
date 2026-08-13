# ETAPA E - Análise Especializada de Degelo

## Fluxo

`CAIXA-PRETA -> TIMELINE -> BASELINE DEGELO -> CICLO -> COMPARAÇÃO -> EVIDÊNCIAS`

O analisador consome somente registros normalizados. Drivers futuros traduzirão sinais
oficiais para marcadores `DEGELO_INICIO`, `DEGELO_FIM`, `GOTEJAMENTO_FIM`,
`RETORNO_REFRIGERACAO` e `RECUPERACAO`. Nenhum endereço ou estado é presumido.

## Fases e dados

- Pré-degelo, degelo, gotejamento, retorno, recuperação e pós-degelo.
- Temperaturas antes, durante e depois; mínimo/máximo durante o ciclo.
- Mudanças de estado de compressor, ventiladores e saídas quando disponíveis.
- Alarmes, qualidade, primeiro desvio, duração e evidências originais.
- Preparado para amostras normalizadas futuras do EM210 total e compressor.

## Classificação

As categorias são independentes: `DIFERENÇA OBSERVADA`, `INDICAÇÃO ESTATÍSTICA`,
`EVIDÊNCIA SUFICIENTE`, `HIPÓTESE` e `DIAGNÓSTICO`. A Etapa E produz somente as
duas primeiras e nunca promove resultados automaticamente.
