# ETAPA H - IA e Detecção de Anomalias

## Papel da camada

`DADOS -> BASELINE -> ANÁLISE ESTATÍSTICA VERSIONADA -> EVIDÊNCIAS -> REVISÃO HUMANA`

A implementação inicial é offline, determinística e explicável. Não usa modelo
generativo, treinamento oculto ou serviço externo. Ela complementa e não substitui o
motor de regras da Etapa G.

## Resultado

Cada análise registra algoritmo/versão, baseline, período, score, classificação,
qualidade, cobertura, confiança, fatores contribuintes, primeiro instante anômalo e
IDs das evidências. Anomalia nunca significa causa-raiz ou diagnóstico confirmado.

## Abstinência

O motor retorna `DADOS INSUFICIENTES / NÃO DETERMINADO` quando faltam amostras,
qualidade, cobertura ou variabilidade de referência. Nenhum valor é preenchido.

## Padrões

Sessões podem ser agrupadas por semelhança de médias normalizadas para encontrar
comportamentos recorrentes. Agrupamentos são descrições de similaridade, não causas.

## Futuro

Qualquer algoritmo mais avançado deverá manter versionamento, auditoria, explicação,
evidências, abstinência e separação entre anomalia, hipótese e diagnóstico.
