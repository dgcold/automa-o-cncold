# ETAPA I - Saúde, Tendências e Assinaturas Operacionais

## Dimensões independentes

Controle, térmica, degelo, compressor, elétrica, comunicação, sensores/dados e geral.
Dimensões ausentes não recebem valor estimado: permanecem `NÃO CONECTADO / SEM DADOS`.

## Significado

Scores são medidas operacionais/estatísticas explicáveis. Não representam chance de
falha. Cada indicador inclui período, qualidade, razões e IDs das evidências.

## Tendências

Evolução de anomalias, alarmes e recuperação é calculada na ordem das sessões. Uma
tendência persistente pode gerar `DEGRADAÇÃO INDICADA`, nunca falha confirmada.

## Assinaturas

Cada sessão produz vetor versionável com médias das variáveis e contagens de alarmes,
desvios, perdas de comunicação e recuperações. Comparações identificam padrões
recorrentes, novos, alterados ou desaparecidos sem atribuir causa.

## EM210

A arquitetura aceita canais normalizados futuros de corrente, tensão, potências, PF,
frequência, energia, sequência de fases e THD. Sem driver/mapa oficial, elétrica e
compressor permanecem sem dados e nenhum registrador é presumido.
