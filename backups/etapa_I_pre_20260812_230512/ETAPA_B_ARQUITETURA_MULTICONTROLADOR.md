# ETAPA B - Arquitetura multicontrolador

## Camadas

```text
CNCold Industrial Diagnostics
|- drivers/
|  |- base.py                         contrato normalizado comum
|  |- registry.py                     seleção sem ativar transporte
|  |- ipro/driver.py                  política FC03/FC04 e candidatos separados
|  `- fullgauge_vx1050e/driver.py     esqueleto sem mapa/transporte presumido
`- camada comum
   |- telemetry.py                    normalização e qualidade
   |- history_store.py                histórico persistente
   |- evidence.py                     eventos/evidências
   |- scenarios.py                    cenários
   |- test_manager.py                 testes
   |- reports.py                      PDF/CSV/JSON
   `- ui.py                           telas compartilhadas
```

## Contrato do driver

Cada driver fornece identidade, configuração, estado do mapa, estado do transporte,
política somente leitura, variáveis normalizadas e diagnóstico de comunicação. A
seleção de um driver constrói apenas estado offline; não conecta rede nem serial.

## Mapas

- `config/controllers/ipro/official_map.json`: vazio, aguardando mapa oficial.
- `config/modbus_map.json`: candidatos iPro existentes, mantidos separadamente.
- `config/controllers/fullgauge_vx1050e/official_map.json`: vazio, aguardando mapa oficial.
- EM210 permanece fora dos controladores de refrigeração e aguarda driver/mapa oficial.

## Segurança

- iPro real: somente FC03/FC04.
- VX-1050E: nenhum transporte ou função presumidos.
- Seleção da interface: `NÃO CONECTADO / SEM MAPA / SEM DADOS`.
- Nenhum driver abre COM8 ou inicia Modbus TCP automaticamente.
