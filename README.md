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
| F7 — Relatório diário no Discord | ✅ |
| F8 — Análise gráfica | ✅ |

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
6. Relatório diário no Discord:
   - No Discord: Editar canal › Integrações › Webhooks › Novo webhook › Copiar URL do webhook, e colar em
     `DISCORD_WEBHOOK_URL` no `backend/.env` (horário em `REPORT_TIME`, padrão 19:00).
   - Agendar no Windows (dias úteis no horário e ao entrar no Windows; dados da CVM a cada 4 semanas):
     ```
     powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1           # criar/atualizar
     powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Remove   # remover
     ```
   - Manual: `uv run python -m app.jobs.daily_report --dry-run` (só mostra), `--now` (envia já). Pela UI, o
     botão de avião no topo abre a prévia e o "Enviar relatório agora". Log em `backend/data/logs/`.
   - **Lista de observação** (aba Observação, ou "Observar" na Análise): ações avisadas só pela distância do preço
     até a MM200, logo depois do relatório. Para um canal próprio, criar outro webhook e colar em
     `DISCORD_WATCHLIST_WEBHOOK_URL` (vazio = mesmo canal do relatório).
7. (Opcional) **Mais de uma carteira** (ex.: a sua e a de um familiar), totalmente separadas, cada uma no próprio
   banco. No `backend/.env`:
   ```
   PROFILES=eu:Eu,familiar:Familiar
   ```
   A primeira usa o banco de `DATABASE_URL`; as outras, o mesmo servidor com o nome + `_id` (`carteira_familiar`).
   Depois rodar (cria os bancos com o superusuário de `POSTGRES_SUPERUSER_PASSWORD`, aplica as migrações em
   todos e carrega os dados da CVM nos novos) e reiniciar o app:
   ```
   cd backend && uv run python -m app.jobs.setup_profiles
   ```
   A troca é pelo seletor ao lado do logo; as outras carteiras ganham uma faixa colorida no topo. O Discord só é
   enviado para a primeira; as outras são atualizadas pelo mesmo job das 19h. Os jobs rodam para todas as
   carteiras (`--profile <id>` para uma só) e `alembic upgrade head` migra todos os bancos.

## Uso diário (atalho)

```
powershell -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1
```
Cria na Área de Trabalho **Carteira B3** (compila a interface se mudou, sobe o backend em segundo plano e abre
http://127.0.0.1:8000) e **Parar Carteira B3**. Nesse modo o próprio backend serve a interface compilada
(`frontend/dist`), um processo só. Logs em `backend/data/logs/`.

## Testes

```
cd backend && uv run pytest
cd frontend && npm run test
```

## API

Com mais de uma carteira, o cabeçalho `X-Profile: <id>` escolhe o banco de cada chamada (sem ele, a primeira).

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/profiles` | Carteiras configuradas (`PROFILES`) |
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
| GET | `/api/report/preview` | Prévia do relatório diário (Markdown do Discord, já dividido em mensagens) |
| POST | `/api/report/send` | Enviar o relatório agora (manual; não conta como o envio agendado) |
| GET | `/api/report/dispatches` | Últimos envios (agendado/manual, enviado/falhou, atrasado) |
| GET/POST | `/api/watchlist` | Lista de observação com a distância até a MM200 / adicionar ação |
| PATCH/DELETE | `/api/watchlist/{ticker}` | Editar a nota / tirar da lista |
| GET/POST | `/api/watchlist/preview`, `/api/watchlist/send` | Prévia do aviso / enviar agora |

Valores monetários e quantidades trafegam como **string decimal** (nunca float).

## Regras de análise (v4)

As notas seguem `backend/rules_config/stocks.yaml` (detalhes no `CLAUDE.md` §5): pesos próprios por setor (geral,
financeiro, utility e cíclico), indicador inválido vale zero (ex.: P/L com prejuízo), checagem de valores implausíveis,
eliminatórios E1, E2, E3 e E5 (lucro, patrimônio, dívida e recuperação judicial/falência; a liquidez diária só é exibida) e nota final 0,6 × Qualidade + 0,4 × Preço.
A nota de Preço é 75% fundamentos e 25% análise gráfica: distância do preço até a MM200 diária (10% abaixo = 100,
na média = 50, 10% acima = 0). A tela de Análise mostra a MM200 no gráfico e a conta passo a passo.

A tela de Análise segue o estilo do Investidor10: primeiro a análise por regras; depois o painel com todos os
indicadores por tema, cotação de até 5 anos, gráficos anuais (receita e lucro, ROE e margens, proventos por ação e DY)
e o histórico dos principais indicadores (tendência de 5 anos, ou tabela ano a ano). Depois de atualizar o código, rodar `uv run alembic upgrade head` e
`uv run python -m app.jobs.ingest_cvm` (recalcula fluxo de caixa e capex a partir dos arquivos já baixados).

## Privacidade

Extratos reais (de qualquer carteira), prints e o `.env` nunca vão para o repositório (ver `.gitignore`). As fixtures de teste da B3
são sintéticas — mesmo layout dos arquivos reais, carteira fictícia.
