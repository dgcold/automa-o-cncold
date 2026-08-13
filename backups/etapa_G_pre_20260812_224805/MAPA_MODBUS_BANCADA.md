# Mapa Modbus de bancada do iPro

## Confirmado pelos arquivos existentes

- Serial: COM8, 9600 baud, 8 bits, paridade N, 2 stop bits.
- O iPro é o MASTER.
- Slave 1 responde exclusivamente a FC04 (Input Registers).
- Slave 2 responde exclusivamente a FC03 (Holding Registers).
- Inícios de bloco vistos no teste:
  - Slave 1: 10, 20, 34, 42, 50, 58, 200, 1200, 1208 e 1216.
  - Slave 2: 256, 261, 263, 272 e 3328.

## Significado dos registradores

Todos os endereços acima permanecem **DESCONHECIDOS**. `slave_teste.py` atribuía
valores sentinela diferentes a cada início de bloco, mas não continha evidência
que ligasse qualquer endereço a temperatura, pressão ou estado específico.

O mapa em `ipro_map.py` também não resolve essa identificação: ele está marcado
no próprio código como provisório, usa endereços diferentes e foi criado para o
notebook operar como cliente de um iPro slave, que é o sentido inverso do teste
de bancada atual.

## Como identificar sem inventar

1. Inicie o painel "Simulador Slave 1/2" e o servidor.
2. Observe no log endereço e quantidade pedidos pelo iPro.
3. Associe temporariamente somente um sinal a um endereço e varie seu valor.
4. Confirme no display/tela do iPro qual grandeza mudou.
5. Repita valores positivos, negativos e pelo menos duas escalas para determinar
   sinal, escala e unidade.
6. Registre a associação no painel; ela será persistida em
   `config_simulador_ipro.json` com status `DEFINIDA_PELO_USUARIO`.

Para tornar uma associação tecnicamente confirmada ainda faltam: captura completa
das requisições (incluindo quantidade), reação observada no iPro para cada valor,
escala/unidade e, idealmente, o manual ou mapa Modbus do equipamento slave original.

## Comparação automática por posição

O painel permite capturar dois estados sem interromper o servidor da COM8:

1. Ajuste o primeiro valor de teste (por exemplo, +20 °C) e clique em
   **Capturar Estado A**. Aguarde o iPro completar pelo menos um ciclo.
2. Ajuste o segundo valor (por exemplo, -30 °C), clique em
   **Capturar Estado B** e aguarde outro ciclo.
3. Clique em **Comparar A × B**.

A tabela compara cada posição do bloco separadamente. Para `END=10 QTD=6`, ela
mostra posições 0 a 5 e endereços efetivos 10 a 15. Linhas alteradas ficam
destacadas. O resultado e as capturas brutas são gravados em `capturas_rs485/`
como CSV e JSON. A comparação detecta mudanças; ela não atribui significado às
posições e, portanto, não cria associações não confirmadas.

A primeira resposta recebida de cada bloco é congelada em cada estado. Alterar o
controle para preparar o Estado B não sobrescreve os blocos já capturados em A.
