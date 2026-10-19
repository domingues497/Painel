# Painel Zabbix — arquitetura modular

## Estrutura
- `app.py`: inicializa FastAPI e registra os routers.
- `config.py`: lê as configurações e o `.env`.
- `services/zabbix_client.py`: centraliza chamadas JSON-RPC à API do Zabbix.
- `services/dashboard.py`: lógica de negócio, transformação dos dados, cache e dados de demonstração.
- `routers/switches.py`: endpoint `/api/switches`.
- `routers/hosts.py`: endpoint `/api/hosts`.
- `routers/network.py`: endpoint `/api/network`.
- `routers/executive.py`: endpoint `/api/executive`.
- `routers/pages.py`: páginas HTML.

## Configurar e executar (PowerShell)
```powershell
Copy-Item .env.example .env  # apenas na primeira execução
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Acesse `http://localhost:8000/`. Se `ZABBIX_URL` estiver vazia, o painel usa dados de demonstração.
Preencha `ZABBIX_URL` e `ZABBIX_TOKEN` no `.env` para conectar ao Zabbix. Use token de conta dedicada com permissões mínimas de leitura. Não versionar nem compartilhar o `.env`.

## Endpoints
- `GET /api/switches`
- `GET /api/hosts?kind=all` (`server`, `workstation` e `other` também são aceitos)
- `GET /api/network`
- `GET /api/executive?days=7&unit=&criticality=`
- `GET /docs` para documentação OpenAPI
