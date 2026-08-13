# Diagnóstico iPro TCP profissional - somente leitura

## Segurança

O módulo `leitor_ipro_tcp.py` aceita exclusivamente FC03 e FC04. FC05, FC06,
FC15 e FC16 são bloqueadas antes da criação de qualquer quadro TCP. O servidor
RS485 em COM8 não é importado, aberto ou modificado pelo diagnóstico.

## Comandos

Somente conexão TCP, sem requisição Modbus:

```powershell
python .\diagnostico_ipro_tcp_profissional.py --somente-conexao
```

Leitura mínima controlada das duas funções permitidas:

```powershell
python .\diagnostico_ipro_tcp_profissional.py --unit-id 1 --endereco 0 --quantidade 1
```

Uma função específica:

```powershell
python .\diagnostico_ipro_tcp_profissional.py --funcao 4 --unit-id 1 --endereco 0 --quantidade 1
```

Captura antes/depois da mesma faixa, sem alterar o iPro:

```powershell
python .\diagnostico_ipro_tcp_profissional.py --comparar --espera 5 --unit-id 1 --endereco 0 --quantidade 1
```

Cada execução cria um JSONL novo em `evidencias_tcp_ipro`. O arquivo inclui
endpoint, Unit ID, função, endereço, quantidade, requisição/resposta hexadecimal,
valores unsigned/signed, latência, exceção Modbus e erro técnico completo.

Uma diferença detectada pela comparação recebe apenas `CANDIDATO`. O programa
não modifica `MATRIZ_COMPLETA_BANCADA_IPRO.md` e nunca confirma associação.
