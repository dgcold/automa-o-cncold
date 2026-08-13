# Matriz completa da bancada iPro

## Escopo e regra de evidência

Esta matriz cruza, sem instalar ou executar a v108 no controlador, quatro fontes independentes:

1. diagrama elétrico `CN 4000 LT BREAD LIFE-atualizada.pdf` (19 páginas);
2. pacote offline v108 e sua interface web;
3. `RELATORIO_W1_W2_W3_RS485.md`;
4. capturas reais do iPro v107 como mestre Modbus RTU.

`CONFIRMADA` significa ligação expressa na fonte citada. `PROVÁVEL` exige evidência indireta forte. `EM TESTE` é uma associação manual de bancada ainda sem correlação observada no iPro. `DESCONHECIDA` significa que a fonte necessária não existe ou ainda não foi capturada. Um índice `W1[n]` nunca é tratado como endereço Modbus.

## Entradas analógicas e grandezas calculadas

| Sinal | Tipo | Origem no PDF | Terminal / I-O | sns[] | W1[] | Unidade | Escala W1 | Registrador RS485 | Confiança | Evidência |
|---|---|---|---|---:|---:|---|---|---|---|---|
| Temperatura Ambiente | entrada NTC | S2, Evaporador 1 | X1:30 / Pb1, CPU pino 2 | 1 | 0 | °C | ÷10 | S1/FC04/reg.10, posição 0 | EM TESTE | PDF p.15; `offset_br.html:195-209`; `monit_br.html:1033-1037`; associação manual em `config_simulador_ipro.json`. Falta observar W1[0] acompanhar dois valores RTU distintos. |
| Temperatura de Degelo | entrada NTC | S3, Evaporador 1 | X1:30 / Pb2, pino 3 | 2 | 4 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:228-242`; `monit_br.html:1084-1089`. |
| Temperatura de Descarga | entrada PTC | S4, Condensador | X1:31 / Pb3, pino 4 | 3 | 8 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:261-275`; `monit_br.html:1140-1145`. |
| Temperatura de Sucção | entrada NTC | S5, Evaporador 1 | X1:31 / Pb4, pino 5 | 4 | 17 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:294-308`; `monit_br.html:1305-1310`. |
| Pressão de Sucção | entrada 0–5 V | P4, Evaporador 1 | X1:32 / Pb5, pino 6 | 5 | 13 | bar | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:327-341`; `monit_br.html:1222-1227`; `param.conf:93-136`. |
| Pressão de Descarga | entrada 0–5 V | P5, Condensadora | X1:32 / Pb6, pino 10 | 6 | 10 | bar | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:360-374`; `monit_br.html:1168-1173`; `param.conf:93-136`. |
| Temperatura de Líquido | entrada NTC | S6, Condensadora | X1:33 / Pb7, pino 11 | 7 | 19 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:393-407`; `monit_br.html:1333-1338`. |
| Temperatura Externa | entrada NTC | S7, Condensador | X1:33 / Pb8, pino 12 | 8 | 6 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.15; `offset_br.html:426-440`; `monit_br.html:1112-1117`. |
| Temperatura de Insuflamento | entrada NTC | S8, Evaporador 1 | X1:34 / Pb9, pino 13 | 9 | 15 | °C | ÷10 | DESCONHECIDO | CONFIRMADA até W1; RS485 DESCONHECIDO | PDF p.16; `offset_br.html:459-473`; `monit_br.html:1277-1282`. |
| Umidade Ambiente | entrada opcional | Umidade interna | Pb10, pino 14; alimentação indicada em X1:12 | 10 | 2 | % | ÷10 | DESCONHECIDO | CONFIRMADA até W1; borne de sinal e RS485 DESCONHECIDOS | PDF p.16 não mostra instrumento/borne de sinal; `offset_br.html:492-506`; `monit_br.html:1056-1061`. |
| Temperatura de Condensação | calculada | não é I/O físico identificado | N/A | — | 12 | °C | ÷10 | DESCONHECIDO | CONFIRMADA somente em W1 | `monit_br.html:1196-1197`; fórmula e origem interna não aparecem no pacote legível. |
| Temperatura de Evaporação | calculada | não é I/O físico identificado | N/A | — | 23 | °C | ÷10 | DESCONHECIDO | CONFIRMADA somente em W1 | `monit_br.html:1250-1251`. |
| Superaquecimento | calculada | não é I/O físico identificado | N/A | — | 24 | K | ÷10 | DESCONHECIDO | CONFIRMADA somente em W1 | `monit_br.html:1362-1363`. |
| Sub-resfriamento | calculada | não é I/O físico identificado | N/A | — | 25 | K | ÷10 | DESCONHECIDO | CONFIRMADA somente em W1 | `monit_br.html:1389-1390`. |
| Setpoint de temperatura | parâmetro interno | não é I/O físico identificado | N/A | — | 26 | °C | ÷10 | DESCONHECIDO | CONFIRMADA somente em W1 | `monit_br.html:999-1000`. |

## Entradas digitais de proteção e comando

| Sinal | Tipo | Origem no PDF | Terminal / I-O | sns[] | W1[] | Unidade | Escala | Registrador RS485 | Confiança | Evidência |
|---|---|---|---|---|---|---|---|---|---|---|
| Partida remota | entrada digital | comando externo | X1:20 / DI1, pino 40 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. Polaridade lógica e transporte RTU não informados. |
| Falta/sequência de fase OK | entrada digital | relé monitor de fase | X1:20 / DI2, pino 41 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.6 e p.14. |
| Termistores do evaporador | proteção | V3–V6 | X1:21 / DI3, pino 42 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. |
| Falha no compressor | proteção | termistores V1/V2 | X1:21 / DI4, pino 43 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. |
| Termistores do condensador | proteção | cadeia do condensador | X1:22 / DI5, pino 44 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. |
| Pressão baixa compressor OK | proteção opcional | pressostato de baixa | X1:22 / DI6, pino 45 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. |
| Pressão alta compressor OK | proteção | P3 | X1:23 / DI7, pino 46 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.14. |
| Alarme de óleo compressor | proteção | Bitzer DELTA P2 | X1:23 / DI8, pino 47 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.7 e p.14. |

## Saídas do controlador

| Sinal | Tipo | Origem no PDF | Terminal / I-O | sns[] | W1[] | Unidade | Escala | Registrador RS485 | Confiança | Evidência |
|---|---|---|---|---|---:|---|---|---|---|---|
| Liga compressor partida 1 | relé | compressor | X1:40 / RL1, pino 70 | — | 44 (status) | estado | enumeração web | DESCONHECIDO | PDF e status W1 confirmados; vínculo direto PROVÁVEL | PDF p.17; `monit_br.html:1453-1489`. W1 pode agregar lógica/falhas, não apenas RL1. |
| Liga resistência de cárter | relé | resistência | X1:40 / RL2, pino 72 | — | DESCONHECIDO | estado | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.9 e p.17. |
| Liga ventilador 2 condensador | relé | condensador | X1:41 / RL3, pino 73 | — | 71 (status condensador 2) | estado | enumeração web | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.17; `monit_br.html:1515-1531`. |
| Liga ventiladores evaporador 1 | relé | evaporador | X1:41 / RL4, pino 76 | — | 41 | estado | enumeração web | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.17; `monit_br.html:1434-1450`. |
| Desumidificador | relé opcional | desumidificação | X1:42 / RL5, pino 77 | — | 60 | estado | enumeração web | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.17; `monit_br.html:1587-1603`. |
| Gás quente / quatro vias (degelo) | relé | Y3/circuito de degelo | X1:42 / RL6, pino 78 | — | 56 | estado | 0/1/2 | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.12 e p.17; `monit_br.html:1551-1567`. |
| Solenoide do evaporador/refrigeração | relé | Y4 | X1:43 / RL7, pino 79 | — | 66 | estado | 0/1 | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.12 e p.17; `monit_br.html:1623-1636`. |
| RL8 | relé sem função desenhada | — | X1:43 / RL8, pino 81 | — | DESCONHECIDO | — | — | DESCONHECIDO | DESCONHECIDA | PDF p.17 deixa a função em branco. |
| Sistema OK sem falhas | relé | indicação externa | X1:44 / RL9 ou RL10 | — | DESCONHECIDO | estado | — | DESCONHECIDO | função CONFIRMADA; relé exato DESCONHECIDO | PDF p.18 agrupa RL9/RL10 no borne 44 sem individualizar inequivocamente a legenda. |
| Liga ventilador 1 condensador | relé | condensador | X1:46 / RL13, pino 89 | — | 50 | estado | enumeração web | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.18; `monit_br.html:1497-1513`. |
| Reserva | relé | reserva | X1:47 / RL15, pino 92 | — | DESCONHECIDO | — | — | DESCONHECIDO | CONFIRMADA no PDF | PDF p.18. RL11, RL12 e RL14 também não têm função identificada. |
| Compressor variável | saída analógica opcional | inversor/compressor | X1:50 / OUT1, pino 21 | — | 47 | % | web sem escala adicional | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.19; `monit_br.html:1491-1495`. Tipo elétrico da saída não indicado. |
| Válvula de expansão eletrônica 2 | saída analógica opcional | VEE 2 | X1:50 / OUT2, pino 22 | — | DESCONHECIDO | % | DESCONHECIDA | DESCONHECIDO | CONFIRMADA no PDF | PDF p.19. Não equiparar automaticamente a W1[54]. |
| Condensador variável 1 | saída analógica | ventilador condensador | X1:51 / OUT3, pino 23 | — | 53 | % | web sem escala adicional | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.19; `monit_br.html:1533-1537`. |
| Controle de capacidade 1 | saída analógica | capacidade | X1:51 / OUT4, pino 24 | — | DESCONHECIDO | % | DESCONHECIDA | DESCONHECIDO | CONFIRMADA no PDF | PDF p.19. |
| Controle de capacidade 2 | saída analógica | capacidade | X1:52 / OUT5, pino 26 | — | DESCONHECIDO | % | DESCONHECIDA | DESCONHECIDO | CONFIRMADA no PDF | PDF p.19. |
| Condensador variável 2 | saída analógica | ventilador condensador | X1:52 / OUT6, pino 27 | — | 55 | % | web sem escala adicional | DESCONHECIDO | PDF e W1 confirmados; vínculo direto PROVÁVEL | PDF p.19; `monit_br.html:1539-1543`. |

## Equipamentos auxiliares e redes encontradas

| Equipamento | Função | Comunicação / ligação confirmada | Endereço Modbus | Evidência |
|---|---|---|---|---|
| WEG CFW500 | inversor do compressor M1 Bitzer 6FE-44Y | RS485 A/B, além de AI1/AO1 e I/O digitais | DESCONHECIDO | PDF p.7. |
| WEG U1/U2 | inversores dos ventiladores condensadores | potência e comando desenhados | DESCONHECIDO | PDF p.8. |
| Full Gauge VX-1050e plus | refrigeração/expansão/hot gas/condensador | RS485 A/B; P1 pressão de sucção; válvula CAREL Y2 | DESCONHECIDO | PDF p.10. |
| CAREL EVD Evolution | driver da válvula Y1 | Modbus RS485 Tx/Rx +/− | DESCONHECIDO | PDF p.11. |

## Blocos RTU realmente observados

| Escravo | Função | Inícios de bloco observados | Significado das posições |
|---:|---:|---|---|
| 1 | FC04 | 10, 20, 34, 42, 50, 58, 200, 1200, 1208, 1216 | DESCONHECIDO; reg.10/posição 0 está apenas EM TESTE como Temperatura Ambiente. |
| 2 | FC03 | 256, 261, 263, 272, 3328 | DESCONHECIDO. |

Comunicação preservada: COM8, 9600 baud, 8 bits, paridade N, 2 stop bits. O simulador responde às leituras; esta matriz não autoriza FC05, FC06, FC15 ou FC16 contra o iPro.

## O que falta para fechar o mapa RS485

Para cada posição de cada bloco é necessário: congelar um estado A, alterar somente uma posição RTU, congelar um estado B, comparar todas as posições e observar simultaneamente o `W1[n]` correspondente na v107. A associação só deve ser promovida a `CONFIRMADA` após duas mudanças reprodutíveis (incluindo valor negativo quando aplicável), escala coerente e ausência de alterações colaterais. Para saídas e estados digitais, também é necessária a correlação temporal com a tela/estado físico do iPro, sem escrever no controlador.
