# ETAPA D - Baseline Operacional

## Fluxo obrigatório

`SESSÃO -> BASELINE CANDIDATO -> VALIDAÇÃO -> BASELINE VALIDADO -> BASELINE ATIVO`

Nenhuma etapa é automática. A ativação exige uma transição explícita de um baseline
já validado. Para substituição, o baseline ativo anterior deve ser arquivado.

## Contextos isolados

- Operação normal
- Partida
- Degelo
- Pós-degelo
- Recuperação

Versão e baseline ativo são independentes por controlador, máquina e contexto.

## Elegibilidade da sessão

São recusadas sessões não finalizadas, com dados insuficientes, alarmes relevantes,
perda de comunicação, desvio previamente marcado ou menos de 80% de amostras úteis.
As sessões da Caixa-Preta são somente consultadas e não sofrem alteração.

## Perfil e comparação

Cada variável registra média, mínimo, máximo, dispersão, faixa normal, tendência,
duração, qualidade e IDs das evidências originais. A comparação informa magnitude,
duração, primeiro instante, contexto, qualidade e evidências. O resultado é rotulado
como indicação estatística ou evidência suficiente, mas nunca como diagnóstico ou
causa-raiz.
