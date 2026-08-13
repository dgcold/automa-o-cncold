# ETAPA G - Diagnóstico Explicável

## Fluxo

`EVIDÊNCIAS ORIGINAIS -> FATOS RASTREÁVEIS -> REGRAS VERSIONADAS -> HIPÓTESES -> REVISÃO HUMANA`

Cada hipótese registra regra/versão, confiança, argumentos favoráveis e contrários,
IDs de evidência, primeiro desvio, contexto, lacunas, teste recomendado e estado.

## Estados

`OBSERVADO`, `INDICAÇÃO`, `HIPÓTESE`, `HIPÓTESE DESCARTADA`,
`EVIDÊNCIA SUFICIENTE` e `CONFIRMADO` são estados separados. Confiança alta não muda
estado. Confirmação exige transição humana explícita e evidência adicional informada.

## Regras

O catálogo padrão está vazio e marcado `AGUARDANDO REGRAS TÉCNICAS VALIDADAS`.
Nenhuma hipótese específica de refrigeração foi inventada. Regras futuras devem possuir
fonte, versão, contexto, fatos favoráveis/contrários, requisitos e teste recomendado.

## Auditoria

Conclusões e transições são persistidas separadamente da Caixa-Preta. Toda mudança
registra data, ação, ator, notas e snapshot completo. As evidências originais são
consultadas sem alteração.
