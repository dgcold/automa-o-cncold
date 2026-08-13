# Validação física controlada — Temperatura Ambiente

## Limites fixos

- COM8 / 9600 / 8N2.
- Resposta exclusivamente para Slave 1 / FC04 / END 10 / QTD 6.
- Somente o offset 0 é alterado.
- Offsets 1 a 5 são sempre enviados como zero.
- Passos fixos e sequenciais: +20,0; +10,0; 0,0; −10,0; −20,0 °C.
- Espera de 15 segundos após cada aplicação antes de liberar a avaliação manual.
- Nenhuma escrita no iPro e nenhuma alteração automática da matriz.

## Execução

Feche primeiro qualquer outra tela que esteja usando a COM8. Em PowerShell:

```powershell
cd "C:\Users\dougl\Downloads\CNCold_Digital_Twin_iPro_Mapa_Visivel\CNCold Digital Twin iPro"
python .\validacao_fisica_temp_ambiente.py
```

Na tela:

1. clique em **Iniciar COM8**;
2. clique em **Aplicar passo atual**;
3. aguarde a contagem chegar a “pronto para avaliar”;
4. observe no iPro se Temperatura Ambiente / W1[0] acompanhou o valor;
5. escolha exatamente um resultado manual;
6. repita até completar os cinco passos.

Os eventos, respostas e resultados manuais são gravados em
`evidencias_validacao_modbus/temp_ambiente_s1_fc04_r10_*.jsonl`. O arquivo é
incremental: mesmo uma sessão interrompida conserva os passos já registrados.

## Critério de interpretação

- **CONFIRMADO POR TESTE DE BANCADA:** o operador observou W1[0] acompanhar o passo.
- **NÃO CONFIRMADO:** W1[0] foi observável, mas não acompanhou o passo.
- **NÃO VALIDADO:** não foi possível observar W1[0] com segurança.

A ferramenta apenas registra essas escolhas. A promoção posterior da matriz deve
ser uma revisão humana do conjunto completo de evidências, nunca uma consequência
automática de um único clique.
