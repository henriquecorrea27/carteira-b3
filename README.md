# Carteira B3

App pessoal, local e de custo zero para acompanhar a carteira de renda variável da B3, puxar proventos e
eventos corporativos automaticamente, analisar ações por regras e enviar um relatório diário no Discord.

A especificação completa está em [`CLAUDE.md`](CLAUDE.md).

## Status

| Fase | Situação |
|---|---|
| F0 — Setup (repo, PostgreSQL, FastAPI + Alembic, frontend) | ✅ |
| F1 — Motor de carteira, lançamentos manuais (individual e lote), testes numéricos | ✅ |
| F2 — Preços, CDI, painel completo | ✅ |
| F3 — Proventos e eventos automáticos | ✅ |
| F4 — Importador B3 | ✅ backend + tela de importação |
| F5 — Dados da CVM, ticker ↔ CNPJ, setores, indicadores | ✅ |
| F6 — Motor de regras, tela de Análise, decisão na carteira, histórico | ✅ |
| F7 — Relatório diário no Discord | ⏳ |
| F8 — Análise gráfica | ⏳ |

## Requisitos

- Windows com **PostgreSQL 16** como serviço (instalado via `winget install PostgreSQL.PostgreSQL.16`)
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node 20+

## Primeira configuração

1. Criar o usuário e os bancos (como superusuário `postgres`):
   ```sql
   CREATE ROLE carteira LOGIN PASSWORD '...';
   CREATE DATABASE carteira OWNER carteira ENCODING 'UTF8' TEMPLATE template0;
   CREATE DATABASE carteira_test OWNER carteira ENCODING 'UTF8' TEMPLATE template0;
   ```
2. Copiar `backend/.env.example` para `backend/.env` e preencher as URLs do banco.
3. Backend:
   ```
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python -m uvicorn app.main:app --reload
   ```
4. Frontend:
   ```
   cd frontend
   npm install
   npm run dev
   ```
   O frontend chama o backend real. Para ver dados de demonstração, criar `frontend/.env.local` com
   `VITE_USE_MOCKS=true`.
5. Atualizar cotações, IBOV e CDI (também pelo botão "Atualizar preços"):
   ```
   cd backend && uv run python -m app.jobs.update_prices
   cd backend && uv run python -m app.jobs.sync_corporate_events   # proventos e eventos da B3
   cd backend && uv run python -m app.jobs.ingest_cvm              # dados da CVM (~1 min; mensal)
   cd backend && uv run python -m app.jobs.daily_analysis          # regras para as ações da carteira
   ```
   Abrir http://localhost:5180.

## Testes

```
cd backend && uv run pytest
cd frontend && npm run test
```

## API (F1)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/transactions` | Livro de operações (filtros: `ticker`, `type`, `source`, `date_from`, `date_to`) |
| POST | `/api/transactions` | Lançamento individual |
| POST | `/api/transactions/batch` | Lançamento em lote (tudo ou nada; erros apontam a linha) |
| PUT / DELETE | `/api/transactions/{id}` | Editar / excluir (recalcula e valida o livro inteiro) |
| GET | `/api/portfolio/positions` | Posições (qtd, PM, custo, resultado realizado, proventos) |
| GET | `/api/portfolio/summary` | Resumo da carteira |
| GET | `/api/assets/search?q=` | Autocomplete de ativos |
| PATCH | `/api/assets/{ticker}` | Ajustar classe/setor/nome do ativo |
| GET | `/api/portfolio/history`, `/api/portfolio/allocation` | Evolução (TWR vs IBOV/CDI) e alocação |
| GET | `/api/provents`, `/api/provents/summary`, `/api/provents/agenda` | Proventos, resumo e agenda |
| GET | `/api/portfolio/pending` | Pendências (bonificação sem custo, evento não reconhecido) |
| POST | `/api/market-data/refresh`, `/api/corporate-events/sync` | Atualizar cotações / eventos da B3 |
| POST | `/api/import/b3/preview`, `/api/import/b3/commit` | Importar extratos da B3 |
| GET | `/api/fundamentals/{ticker}` | Indicadores fundamentalistas de qualquer ação listada |
| POST | `/api/fundamentals/ingest` | Baixar/processar os dados da CVM (em segundo plano) |
| GET | `/api/analysis/{ticker}` | Decisão por regras com explicação completa (grava o snapshot do dia) |
| POST | `/api/analysis/portfolio` | Reanalisar todas as ações da carteira |
| GET | `/api/prices/{ticker}` | Cotações diárias (OHLC) para o gráfico |

Valores monetários e quantidades trafegam como **string decimal** (nunca float).

## Privacidade

Extratos reais, prints e o `.env` nunca vão para o repositório (ver `.gitignore`). As fixtures de teste da B3
são sintéticas — mesmo layout dos arquivos reais, carteira fictícia.
