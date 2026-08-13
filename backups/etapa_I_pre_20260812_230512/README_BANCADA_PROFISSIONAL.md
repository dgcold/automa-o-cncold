# CNCold iPro Professional Bench

Primeira etapa da plataforma modular de engenharia para bancada iPro. A nova aplicação é separada da interface legada e não inicia comunicação automaticamente.

## Executar

```powershell
& "C:\Users\dougl\AppData\Local\Python\pythoncore-3.14-64\python.exe" bench_main.py
```

## Segurança operacional

- O modo inicial é `SIMULADOR` e a COM8 permanece fechada.
- O modo `REAL / SOMENTE LEITURA` usa exclusivamente o cliente TCP com FC03/FC04.
- Não existem ações FC05, FC06, FC15, FC16, reset, STOP, download ou alteração de parâmetros.
- O mapa ativo contém endereços nulos enquanto o mapa oficial não for recebido.
- Candidatos estruturais ficam separados e nunca são promovidos automaticamente.
- A importação valida e prepara uma versão no histórico, mas não a ativa.

## Estrutura da etapa 1

- `ipro_bench/core.py`: modos, estados de conexão e qualidade.
- `ipro_bench/communication.py`: fachadas para TCP somente leitura e RTU sob demanda.
- `ipro_bench/mapping.py`: validação, diferenças e preparação de mapas versionados.
- `ipro_bench/evidence.py`: evidência JSONL append-only.
- `ipro_bench/test_manager.py`: ciclo de vida rastreável dos testes.
- `ipro_bench/ui.py`: shell profissional, dashboard e telas iniciais.
- `config/modbus_map.json`: mapa configurável inicial.

## Estado funcional

Dashboard, modos, supervisão não mapeada, central de comunicação, mapa/importador, Test Manager, evidências e diagnóstico estão funcionais nesta etapa. I/O e relatórios aparecem como módulos planejados e serão implementados nas próximas etapas.
