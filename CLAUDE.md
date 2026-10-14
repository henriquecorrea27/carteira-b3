# CLAUDE.md — Carteira B3 (nome provisório)

App pessoal, rodando local, para:
1. **Monitorar a carteira** de renda variável da B3 (painel completo no estilo Investidor10), calculando tudo a partir das **operações** (nunca importando a posição pronta).
2. **Puxar automaticamente proventos e eventos corporativos** (dividendos, JCP, rendimentos, desdobramentos, grupamentos, bonificações).
3. **Pesquisar qualquer ação** e mostrar indicadores + **análise baseada em regras** (nota de Qualidade, nota de Preço, decisão COMPRAR / AGUARDAR / EVITAR, e quais indicadores passaram).
4. **Notificar diariamente no Discord** o que está bom ou ruim na carteira para comprar.

Usuário único (o dono). Sem login, sem multi-tenant, sem deploy em nuvem. **Custo zero**: nenhuma API paga.

> Idioma: documentação em português; código, nomes de tabelas, variáveis, commits e comentários em **inglês**.

---

## 1. Stack

| Camada | Escolha | Motivo |
|---|---|---|
| Backend | Python 3.12 + FastAPI | pandas é essencial para os dados da CVM |
| ORM / migrações | SQLAlchemy 2.x + Alembic | |
| Validação | Pydantic v2 | |
| Banco | PostgreSQL 16 instalado no Windows (serviço, via winget) | sobe com o sistema; o job do Discord não depende de nada aberto |
| Jobs | Comandos CLI independentes (`python -m app.jobs.<job>`) + APScheduler quando o backend está rodando | ver seção 6.3 |
| Dados | pandas, yfinance, httpx | |
| Notificações | Discord Webhook (gratuito, URL no `.env`) | |
| Gerenciador de pacotes | uv | |
| Frontend | React + Vite + TypeScript | painel rico (Streamlit não aguenta o nível de UI desejado) |
| UI | Tailwind + shadcn/ui | |
| Data fetching | TanStack Query | |
| Gráficos | Recharts (painel) + TradingView lightweight-charts (preço/candles; base para a análise gráfica da F8) | |
| Testes | pytest (backend), Vitest (frontend) | |

### Estrutura de pastas
```
/backend
  /app
    /api            # routers FastAPI
    /core           # config, db session, logging
    /models         # SQLAlchemy models
    /schemas        # Pydantic
    /portfolio      # motor de carteira (PM, posições, proventos, rentabilidade)
    /corporate_events  # adapters de proventos/eventos + aplicação na carteira
    /importers      # b3_trades, b3_movements (cada um isolado)
    /market_data    # adapters: yfinance, bcb (CDI)
    /fundamentals   # ingestão CVM + cálculo de indicadores
    /rules          # motor de regras + scoring
    /notifications  # discord
    /jobs           # tarefas agendadas (cada uma executável via CLI)
  /rules_config
    stocks.yaml     # regras/pesos/faixas — FONTE DA VERDADE das regras
  /tests
    /fixtures       # fixtures sintéticas (layout real, valores fictícios) e respostas de APIs públicas
/frontend
README.md
CLAUDE.md
```

### Comandos
```
# PostgreSQL 16 roda como serviço do Windows (postgresql-x64-16); bancos: carteira e carteira_test
cd backend && uv sync                              # instala dependências
cd backend && uv run alembic upgrade head          # aplica migrações
cd backend && uv run python -m uvicorn app.main:app --reload # API em http://localhost:8000 (docs em /docs)
cd backend && uv run pytest                        # testes (usa o banco carteira_test)
cd backend && uv run ruff check . && uv run ruff format .
cd backend && uv run python -m app.jobs.update_prices          # cotações, IBOV e CDI
cd backend && uv run python -m app.jobs.sync_corporate_events  # proventos e eventos da B3
cd backend && uv run python -m app.jobs.ingest_cvm             # dados da CVM + indicadores (mensal)
cd backend && uv run python -m app.jobs.daily_analysis         # regras para as ações da carteira (diário)
cd backend && uv run python -m app.jobs.daily_report           # relatório diário (--dry-run mostra, --now envia já)
powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1  # agenda os jobs no Windows (-Remove desfaz)
cd frontend && npm run dev                         # UI em http://localhost:5180 (proxy /api → :8000)
# Uso diário: atalhos "Carteira B3" / "Parar Carteira B3" (scripts/install_shortcuts.ps1). O backend serve o
# frontend compilado (frontend/dist) em http://127.0.0.1:8000; start_app.ps1 recompila se o código mudou.
```

### Ambiente (Windows)
- **Smart App Control está ativo** e bloqueia DLLs sem reputação (ex.: pandas ≥ 2.3 falhou com
  "Uma política de Controle de Aplicativo bloqueou este arquivo"). Ao adicionar/atualizar dependência com
  binário nativo, testar o import; se bloquear, fixar uma versão anterior e anotar o motivo no `pyproject.toml`.
  Ele também bloqueia os `.exe` gerados no venv (ex.: `uvicorn.exe`): rodar sempre como `python -m <ferramenta>`.
- `uv` instalado via winget; se não estiver no PATH do shell, o executável fica em
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*\uv.exe`.
- Segredos do banco em `backend/.env` (gerados na instalação; modelo em `backend/.env.example`).

### Interface (decidido)
- Idioma da UI: **português**; moeda R$ e números no padrão brasileiro (`1.234,56`, `12,5%`), datas `dd/mm/aaaa`.
- **Tema claro e escuro**, com alternância pelo usuário (padrão: seguir o sistema).
- Navegação por **abas no topo** (Carteira, Proventos, Operações, Análise, Importar).
- Referência funcional: Investidor10 (prints enviados pelo usuário); visual **mais moderno e minimalista**.

---

## 2. Regras gerais de código

- **Dinheiro e quantidades: sempre `Decimal`** (Python) e `NUMERIC` (Postgres). Nunca float para valores financeiros. Float só é aceitável dentro do cálculo de indicadores fundamentalistas (ratios), arredondando na saída.
- Toda fonte externa fica atrás de um **adapter com interface** (`MarketDataProvider`, `PortfolioImporter`, `CorporateEventsSource`, `FundamentalsSource`, `Notifier`). Trocar yfinance por brapi, ou adicionar Pluggy, não pode exigir mudança no motor.
- Importações e jobs são **idempotentes**: rodar de novo não duplica nada (hash por linha/evento normalizado).
- Nenhum segredo no repositório; `.env` no `.gitignore`, `.env.example` versionado (inclui `DISCORD_WEBHOOK_URL`).
- Manter **README.md e CLAUDE.md atualizados** ao final de cada fase.
- O motor de carteira (`/portfolio`) é a parte mais crítica: **toda regra de cálculo tem teste com caso numérico fechado** antes de ir para a UI.
- **Nunca adivinhar o layout de arquivos ou de respostas de APIs não documentadas** (exportações B3, endpoints de proventos). Construir parsers a partir de exemplos reais; se não houver, buscar/pedir o exemplo antes de codar.
- **Privacidade dos dados do usuário:** arquivos reais enviados pelo usuário (extratos B3 etc.) **nunca são commitados** e são **apagados após o uso**. As fixtures em `/tests/fixtures` são **sintéticas**: mesmo layout (colunas, tipos, formatos) do arquivo real, com valores fictícios. Respostas de APIs públicas (B3, CVM) podem ser salvas como fixture.
- Repositório GitHub **privado**. Antes de cada commit, conferir que nada pessoal entra (`.env`, extratos, dumps do banco, dados da carteira).
- Falha de fonte externa **nunca derruba o app**: registrar, mostrar aviso na UI e seguir com o último dado em cache.

---

## 3. Módulo Carteira

### 3.1 Princípio
A carteira é **derivada do livro de operações** (`transactions`). Posição, preço médio, lucro realizado e proventos são sempre recalculáveis do zero a partir dele. Nada de "posição importada".

### 3.2 Escopo
- Ativos: **ações, FIIs, ETFs e BDRs** negociados na B3.
- Fora (radar): renda fixa, Tesouro, opções, day trade, aluguel de ações, IR/DARF.

### 3.3 Tipos de lançamento (`transaction_type`)
| Tipo | Efeito |
|---|---|
| `BUY` | aumenta qtd, recalcula PM |
| `SELL` | reduz qtd, PM inalterado, gera lucro/prejuízo realizado |
| `SPLIT` (desdobramento, fator k) | qtd × k, PM ÷ k |
| `REVERSE_SPLIT` (grupamento, fator k) | qtd ÷ k, PM × k; frações vendidas em leilão viram `FRACTION_AUCTION` |
| `FRACTION_AUCTION` | tratado como venda da fração pelo valor creditado |
| `BONUS` (bonificação) | entra qtd nova com **custo unitário atribuído pela empresa** → recalcula PM. Ver 3.9 |
| `TICKER_CHANGE` / incorporação | converte posição de um ticker para outro (fator de conversão), preservando custo total |
| `DIVIDEND`, `JCP`, `INCOME` (rendimento FII) | provento; guardar **bruto, IR retido e líquido** |

**IR sobre proventos (não hardcodar uma alíquota única):**
- JCP: IRRF de **15% para pagamentos até 31/12/2025** e **17,5% a partir de 01/01/2026** (LC 224/2025). A alíquota é escolhida pela **data de pagamento**.
- Dividendos: isentos para o investidor comum. Desde 2026 há retenção de 10% apenas quando uma mesma empresa paga mais de R$ 50 mil no mês à mesma pessoa física (Lei 15.270/2025). Guardar o IR retido quando a fonte informar; não presumir.
- As alíquotas ficam em configuração com vigência por data, nunca espalhadas no código.

### 3.4 Preço médio (custo médio ponderado, padrão Receita Federal)
- Compra: `PM_novo = (qtd_ant × PM_ant + qtd × preço + custos) / (qtd_ant + qtd)`
- Venda: PM não muda. `resultado = (qtd × preço_venda − custos_venda) − qtd × PM`
- Custos (corretagem, emolumentos, taxas) **entram no custo de aquisição**. Campo opcional no lançamento; nota de corretagem fica no radar.
- Ticker fracionário (`PETR4F`) é normalizado para o ticker padrão (`PETR4`).
- Zerou a posição → PM zera; recompra começa PM novo.

**Decisões de implementação (F1, `app/portfolio/engine.py`):**
- Motor puro (sem banco), replay cronológico do livro. Precisão total em `Decimal`; arredonda só na saída da API
  (dinheiro com 2 casas; quantidades/preços até 8 casas, como string no JSON).
- Ordem dentro do mesmo dia: troca de ticker → desdobro/grupamento → bonificação → compras → vendas → leilão de
  fração → proventos. Eventos valem a partir da data ex (negócio no dia ex já está "pós-evento").
- Toda escrita (criar/editar/excluir) refaz o livro inteiro antes de gravar: se quebrar (venda maior que a
  posição, bonificação sem posição), nada é salvo e o erro aponta a linha do lote ou o lançamento afetado.
- Proventos: `date` = data-com; `payment_date` = pagamento; status `ANNOUNCED` conta como "a receber".
  IR do JCP calculado pela tabela `rules_config/tax_rates.yaml` (vigência pela data de pagamento) quando não informado.
- Editar qualquer lançamento marca `user_edited = true` (jobs automáticos nunca sobrescrevem).

### 3.5 Fontes de operações
1. **Lançamento manual** — fonte principal no início. Botões **"Lançar compra"**, **"Lançar venda"** e **"Lançar evento"**.
   - Campos: data, ticker (autocomplete), quantidade, preço unitário, custos (opcional), corretora (opcional), observação.
   - Validações: não permitir venda maior que a posição na data; avisar se o preço estiver muito longe do fechamento do dia (provável erro de digitação).
   - **Lançamento em lote:** tabela editável para digitar várias operações de uma vez antes de salvar.
2. **Importação B3 — Área do Investidor**:
   - Extrato de **Negociação** → `BUY`/`SELL`.
   - Extrato de **Movimentação** → proventos e eventos efetivamente creditados. **Atenção:** a movimentação também contém linhas de liquidação de compras/vendas que já vêm na Negociação — **não contar duas vezes**.
   - Layout e tipos de movimentação **validados com os arquivos reais** (08/10/2026) e documentados em
     `backend/tests/fixtures/b3/README.md` (fixtures sintéticas com o mesmo layout).
   - **Futuros (WDO, WIN…) são ignorados** nos dois extratos: na Negociação, `Mercado = Futuro`; na Movimentação,
     `Produto` começa com `Futuro - ` (todas as linhas `Compra`/`Venda` da Movimentação eram futuros).
   - Renda fixa (`CDB - …`), direitos de subscrição não exercidos e transferências de custódia também são ignorados.
3. **Investidor10:** não tem exportação. Descartado como fonte.

### 3.6 Deduplicação
- Hash por linha normalizada (data, ticker, tipo, qtd, preço, corretora, fonte).
- Lançamento manual parecido com um importado (mesma data/ticker/tipo/qtd) → marcar como **"possível duplicata"** e pedir confirmação na UI; nunca apagar sozinho.

### 3.7 Painel (referência visual: Investidor10)
- **Resumo:** patrimônio atual, total investido, lucro/prejuízo (aberto e realizado), rentabilidade total e no período, proventos recebidos (12m e total), **proventos a receber**.
- **Posição por ativo:** qtd, PM, preço atual, valor, % da carteira, resultado R$ e %, yield on cost, proventos recebidos do ativo, **nota/decisão das regras** (só ações).
- **Alocação:** por classe (ação/FII/ETF/BDR), por setor, por ativo.
- **Evolução do patrimônio** (linha) vs. valor aplicado.
- **Rentabilidade** pelo método de **cotas (TWR)** comparada com **IBOV** (`^BVSP` via yfinance) e **CDI** (API SGS do Banco Central, série 12, gratuita).
- **Proventos:** por mês (barras), por ativo, histórico detalhado, **agenda de próximos pagamentos e datas-com**.
- **Eventos pendentes:** bonificações sem custo atribuído, eventos não reconhecidos, possíveis duplicatas.
- **Livro de operações:** lista filtrável, editar/excluir lançamentos, ver origem de cada linha (manual / B3 / automático).
- **Importar:** upload dos arquivos, prévia antes de gravar, relatório do que foi inserido/ignorado/duplicado.

### 3.8 Preços
- yfinance com sufixo `.SA`. Atualização: job diário após o fechamento + botão "atualizar agora".
- Cache em banco (`price_history`). Nunca chamar a API a cada render.
- Cada atualização busca de novo os últimos 7 dias já em cache (`market_data.service.REVISE`): uma linha gravada
  durante o pregão guarda um preço intradiário e precisa ser trocada pelo fechamento.
- Histórico diário desde a primeira operação, para evolução do patrimônio e TWR.

### 3.9 Proventos e eventos corporativos automáticos
**Objetivo:** o usuário só lança compras e vendas; proventos, desdobramentos, grupamentos e bonificações entram sozinhos.

**Fonte primária:** dados públicos de **proventos em dinheiro e eventos em ações** do site de empresas listadas da B3 (os mesmos que o pacote open source `rb3`, da rOpenSci, consome).
- É um endpoint **público, mas não documentado** → adapter isolado, cache em banco, tolerância a mudança de formato, testes com respostas reais salvas em `/tests/fixtures`.
- **Antes de codar:** inspecionar respostas reais (ex.: PETR4, ITUB4, uma ação com bonificação, um FII, um ETF) e confirmar quais campos existem (tipo, valor por ação, data-com, data de pagamento, fator) e se FIIs/ETFs estão cobertos.
- Se FIIs não estiverem cobertos: rendimentos de FII entram pela importação da Movimentação B3 ou manualmente, até achar outra fonte gratuita.

**Fonte secundária (só conferência):** yfinance (`dividends`, `splits`). **Nunca usar como primária**: não separa bem dividendo de JCP, usa data ex e pode representar bonificação como split, o que zeraria o custo atribuído.

**Lógica:**
1. Job diário busca eventos dos tickers que o usuário tem ou já teve.
2. **Provento em dinheiro:** se a posição no fim da **data-com** > 0 → gera lançamento automático `qtd na data-com × valor por ação`, com IR conforme 3.3.
3. Ciclo de status do provento: `ANNOUNCED` (pagamento futuro, aparece em "a receber") → `PAID` (passou a data de pagamento) → `CONFIRMED` (bateu com a Movimentação da B3, se importada).
4. **Desdobramento/grupamento:** aplicado automaticamente na data ex, com o fator da fonte.
5. **Bonificação:** quantidade aplicada automaticamente. Se a fonte não trouxer o **custo atribuído**, o evento fica **"pendente de custo"** no painel até o usuário informar o valor (está no aviso aos acionistas da empresa). Enquanto pendente, o PM do ativo aparece com aviso.
6. Lançamentos automáticos têm `source = AUTO`, são editáveis, e **edição manual sempre prevalece**: o job não sobrescreve um evento que o usuário alterou.
7. Mudanças nas operações (ex.: compra lançada com data retroativa) disparam recálculo dos proventos afetados.

**Implementação (F3, `app/corporate_events/`):** formato da fonte documentado em
`backend/tests/fixtures/b3_events/README.md` (respostas reais salvas).
- Eventos ficam em cache (`corporate_events`); `apply_events` gera/atualiza/remove os lançamentos `AUTO`
  (`dedup_hash` = chave do evento) e roda após toda escrita no livro e após cada sincronização.
- A fonte só traz proventos em dinheiro dos últimos ~12 meses → o histórico antigo vem da Movimentação B3.
  Por isso a sincronização só consulta empresas com posição aberta ou negociadas nos últimos ~13 meses.
- Data-com futura: aparece só na agenda (estimativa com a posição atual); o lançamento é criado depois dela.
- Valor bruto = qtd × valor por ação **truncado** no centavo; IR do JCP pela tabela de vigência.
- Evento já presente no livro (importado da B3 ou manual, mesmo ticker/tipo, valor por ação ≈ e pagamento
  em até 5 dias; eventos em ações até 30 dias após a data-com) não é gerado de novo; linhas importadas
  recebem a data-com (proventos) ou a data-ex (eventos em ações).
- Data-ex = próximo dia útil da B3 após a data-com (`app/core/calendar.py`, feriados nacionais + 24 e 31/12).
- Excluir um lançamento `AUTO` dispensa o evento para sempre; editar marca `user_edited` e o job não toca mais.
- Importar Movimentação depois: proventos que casam com `AUTO` não editado substituem o `AUTO`; com `AUTO`
  editado, a linha importada é marcada como duplicada.
- Rótulos não tratados (subscrição, resgate etc.) dos últimos 90 dias viram pendência "evento não reconhecido".

---

## 4. Módulo Análise de Ativos

### 4.1 Fontes (todas gratuitas)
| Dado | Fonte |
|---|---|
| DFP (anual), ITR (trimestral) | Portal de Dados Abertos da CVM (`dados.cvm.gov.br/dados/CIA_ABERTA`) |
| Número de ações | CVM (FRE / composição do capital) |
| Ticker ↔ CNPJ | CVM FCA (valores mobiliários) |
| Setor | CVM cadastro (`SETOR_ATIV`) + override manual |
| Preço, volume | yfinance |
| Proventos por ação (para DY e Bazin) | mesma fonte da seção 3.9 |

**Cuidados com a CVM:**
- Preferir demonstrações **consolidadas**; cair para individuais só se não houver.
- Usar sempre a **última versão** do documento (refazimentos).
- Atenção à **escala** (unidade vs. milhar).
- TTM = soma dos últimos 4 trimestres; o 4º trimestre = DFP anual − ITR acumulado de 9 meses.
- D&A não tem código padronizado na DFC: localizar pela descrição da conta e registrar quando não encontrar.
- Ingestão: job mensal + botão manual. Guardar dados brutos e indicadores calculados separadamente.

**Implementação (F5, `app/fundamentals/`)** — layout real documentado em `backend/tests/fixtures/cvm/README.md`:
- Arquivos brutos da CVM ficam em cache em `backend/data/cvm/raw` (fora do git; rebaixados só quando a CVM
  republica). Dados extraídos por período em `fundamental_periods`; indicadores calculados sob demanda.
- Lê DFP dos últimos 6 anos (médias de 5 anos + base do CAGR) e ITR do ano atual e do anterior.
- Contas localizadas por nível + descrição (os códigos variam entre empresas, bancos e seguradoras).
- **Número de ações: B3** (dados da empresa listada, em unidades). A `composicao_capital` da CVM mistura
  unidades e milhares sem indicar a escala → só serve de reserva (escala deduzida pelo LPA declarado) e para as
  ações em tesouraria.
- **Dividendos pagos: DFC individual (controladora)** — a consolidada inclui o que as controladas pagam aos
  minoritários delas (ex.: holding Metalúrgica Gerdau).
- **DY médio 5a e Bazin:** a fonte da seção 3.9 (B3) só tem ~12 meses de proventos, então os proventos por ação
  de 5 anos = dividendos + JCP pagos (DFC da controladora) ÷ ações atuais.
- TTM = acumulado do último ITR + último DFP − mesmo acumulado do ano anterior.
- Setor especial (FINANCIAL, UTILITY, CYCLICAL): classificado pelas regras do `stocks.yaml` (seção 5.3).
- Ativos da carteira que são ações listadas recebem o setor da CVM e a classe STOCK (corrige units "11").
- **Fluxo de caixa (v2):** FCO = conta 6.01 ("Caixa Líquido Atividades Operacionais"); capex = soma das saídas em 6.02
  cuja descrição cita imobilizado, intangível, software, ativos de contrato ou infraestrutura (exclui alienação, venda,
  aquisição de controladas). Validado em arquivos reais (Petrobras, Vale, Ambev, WEG, Cemig, Equatorial, B3…).
- **Proventos pagos:** além de "dividendos" e "JCP", aceita "Pagamento de Proventos" (B3), "Juros s/ o capital
  próprio" (ABC), "Pagamento e remuneração aos acionistas" (Axia) e "Distribuição de lucros". Se a CVM somar zero mas
  a B3 listar proventos nos últimos ~12 meses (`companies.b3_pays_dividends`), o DY vira N/A com aviso.
- Linha "atribuído aos controladores" preenchida com zero (comum em bancos) → lucro dos controladores = lucro total.
- Situação do emissor (`companies.issuer_status`) vem do `SIT_EMISSOR` do cadastro (regra E5).

### 4.2 Definição dos indicadores
| Indicador | Fórmula |
|---|---|
| ROE (exibido) | Lucro líquido TTM / PL médio |
| ROE médio 5a (usado na nota) | média dos ROEs anuais dos últimos 5 DFPs (lucro do ano / PL médio do ano) |
| ROIC | EBIT TTM × (1 − 0,34) / (PL + dívida bruta − caixa) |
| Margem líquida | Lucro líquido / Receita líquida (média 5 anos) |
| CAGR lucro / receita | anual, 5 anos, base DFP. Base ≤ 0 → N/A |
| Dívida líquida / EBITDA | (empréstimos + financiamentos + debêntures, CP+LP − caixa e aplicações) / (EBIT + D&A) TTM. Excluir arrendamentos IFRS 16 |
| Liquidez corrente | Ativo circulante / Passivo circulante |
| Payout | (Dividendos + JCP) / Lucro líquido, média 5 anos |
| P/L | Preço / LPA TTM (só se LPA > 0) |
| P/VP | Preço / VPA |
| EV/EBIT | (Valor de mercado + dívida líquida + participação dos minoritários) / EBIT TTM |
| Valor de mercado | Σ (ações de cada classe, excluindo tesouraria × preço da classe) |
| Preço justo Graham | √(22,5 × LPA × VPA). LPA ou VPA ≤ 0 → N/A |
| Margem de segurança Graham | (preço justo − preço) / preço |
| DY médio 5a | Proventos brutos por ação médios dos últimos 5 anos / preço atual |
| Preço teto Bazin | Proventos por ação médios 5a / 0,06 (exibir na tela) |
| Liquidez diária | Média do volume financeiro (preço × volume) dos últimos 2 meses |
| FCO / lucro 5a | Σ fluxo de caixa operacional (DFC 6.01) / Σ lucro líquido consolidado, últimos 5 DFPs (mín. 3) |
| FCF yield | (FCO − capex) TTM / valor de mercado. Capex = saídas de imobilizado, intangível e ativos de contrato (DFC 6.02) |
| Quedas de lucro 5a | Nº de anos (em 5) com lucro < 75% do ano anterior (ou prejuízo após lucro); exige 6 DFPs |
| CAGR do patrimônio | Como o CAGR do lucro, sobre o PL dos controladores |
| PL / ativo total | PL / ativo total do último balanço (bancos) |
| Múltiplos normalizados | P/L sobre o lucro médio de 5a; EV/EBIT sobre o EBIT médio de 5a; Dív. líq./EBITDA médio de 5a (cíclicas) |

---

## 5. Motor de Regras — v4 (pesos por setor + MM200, sem eliminatório de liquidez)

> Pesos, faixas e travas propostos pelo agente `analista-investimentos` (`.claude/agents/`) e **aprovados pelo
> usuário em 10/10/2026**. **Não alterar pesos, faixas ou limites sem decisão explícita do usuário.**
> A implementação lê tudo de `rules_config/stocks.yaml`. Qualquer mudança aprovada deve ser feita no YAML **e** nesta seção
> (e no teste `test_approved_weights_v2`).
> A análise gráfica (F8, MM200) foi especificada pelo usuário em 13/10/2026 e entra como componente da nota de Preço
> com peso 0,25 (seção 5.6). O eliminatório de liquidez diária (antigo E4) foi **removido pelo usuário em 14/10/2026**:
> a liquidez continua exibida e serve de desempate, mas não elimina. Versão do YAML: 4.
> **Revisão:** 30/04/2027 (após a temporada de DFP 2026), ou antes se a Selic sair de 11–17%, o IPCA 12m passar de 6%,
> mudar a tributação de dividendos/JCP, mudar o layout da CVM ou mais de 10% da carteira ficar inconclusiva.

### 5.1 Pontuação gradual
- Cada indicador tem faixa **"ruim"** e **"ótimo"**. Pontuação = interpolação linear entre as duas, limitada a [0, 1], × peso.
- Nota = soma dos pontos obtidos / soma dos pesos avaliados × 100. Cada grupo (Qualidade, Preço) soma 100 em cada setor.
- Status exibido: ✅ ≥ 70% dos pontos · ⚠️ 30–70% · ❌ < 30% · ➖ sem dados.
- **Indicador sem dados (N/A)** sai do denominador e aparece como "sem dados". Se mais de 30% do peso de uma nota estiver N/A → nota marcada **"inconclusiva"** e decisão = AGUARDAR.
- **Inválido ≠ ausente:** P/L com LPA ≤ 0, EV/EBIT com EBIT ≤ 0, CAGR com valor final ≤ 0 (base > 0), Dív/EBITDA com
  EBITDA ≤ 0 e payout sem ano de lucro valem **0 ponto (❌)** e ficam no denominador (`if_invalid: zero` no YAML).
  CAGR com base ≤ 0 continua N/A.
- **Valor implausível** (P/L < 1,5, P/VP < 0,1, DY > 25%, EV/EBIT entre 0 e 0,5) → N/A com aviso
  "valor implausível — conferir nº de ações" (típico de número de ações em escala errada).
- **Peso 0** = só exibido (margem de Graham, que é P/L × P/VP de novo).
- **Travas:** eliminatório reprovado → nota final ≤ 30; LPA TTM ≤ 0 → nota de Preço ≤ 40 (nunca COMPRAR).
- **Dados defasados:** último balanço com mais de 8 meses, ou sem DFP do último ano após 15/05 → as duas notas ficam
  inconclusivas (AGUARDAR) com aviso.
- Regra cujo indicador o motor não calcula é ignorada (os pesos se reponderam), nunca contada como N/A.

### 5.2 Camada 1 — Eliminatórios (falhou em qualquer um → EVITAR)
| ID | Regra | Limite |
|---|---|---|
| E1 | Lucro líquido positivo nos últimos 5 anos | ≥ 4 de 5 anos |
| E2 | Patrimônio líquido | > 0 |
| E3 | Dívida líquida / EBITDA (EBITDA ≤ 0 reprova) | ≤ 3,5 (utility ≤ 4,5; cíclica ≤ 3,0 sobre o EBITDA médio de 5 anos) |
| E5 | Emissor sem recuperação judicial/extrajudicial, falência, liquidação ou paralisação | `SIT_EMISSOR` do cadastro da CVM + lista manual por ticker (AMBP: RJ desde 10/2025, a CVM ainda mostra "fase operacional") |

### 5.3 Classificação de setor
Pelo `SETOR_ATIV` da CVM (sem acento; holdings "Emp. Adm. Part. - <setor>" seguem o setor principal). A primeira que casar vence:
1. **FINANCEIRO:** plano de contas de banco, ou bancos, seguradoras, intermediação financeira, arrendamento mercantil,
   previdência, capitalização, crédito imobiliário.
2. **UTILITY:** energia elétrica, saneamento, água e gás.
3. **CÍCLICA:** metalurgia e siderurgia, extração mineral, petróleo e gás, papel e celulose, petroquímicos, agricultura,
   reflorestamento.
4. **GERAL:** o resto. Override manual por raiz de ticker no YAML (AMBP → GERAL; a Ambipar está cadastrada como saneamento).

### 5.4 Pesos e faixas (ruim → ótimo)
**GERAL — Qualidade:** ROIC 20 (6% → 16%) · ROE médio 5a 10 (8% → 20%) · margem líquida 5a 5 (5% → 15%) ·
Dív. líq./EBITDA 20 (3,0 → 0,5) · liquidez corrente 5 (0,8 → 1,5) · CAGR receita 5a 10 (5% → 15%) ·
CAGR lucro 5a 10 (5% → 18%) · FCO/lucro 5a 10 (0,6 → 1,0) · quedas de lucro > 25% em 5a 5 (3 → 0) ·
payout 5a 5 (ótimo 25–80%, zero fora de 0–100%).
**GERAL — Preço:** EV/EBIT 30 (15 → 6) · P/L 20 (20 → 7) · DY médio 5a 20 (2% → 8%) · P/VP 10 (3,0 → 1,0) ·
FCF yield 20 (2% → 10%) · margem de Graham 0 (só exibida).

**FINANCEIRO** (aviso "análise parcial"; eliminatórios E1, E2, E5) — Qualidade: ROE 5a 45 (10% → 20%) ·
CAGR lucro 20 (5% → 15%) · CAGR do patrimônio 15 (4% → 12%) · PL/ativo total 10 (6% → 10%, **só bancos**) ·
payout 10 (ótimo 25–90%, zero fora de 0–110%). Preço: P/L 40 (15 → 6) · DY 40 (3% → 9%) · P/VP 20 (2,5 → 0,9).

**UTILITY** — Qualidade: ROIC 20 (5% → 12%) · ROE 5a 15 (8% → 18%) · Dív./EBITDA 25 (4,5 → 2,0) ·
liquidez corrente 5 (0,6 → 1,2) · CAGR receita 5 (5% → 12%) · CAGR lucro 10 (5% → 15%) · payout 10 (ótimo 40–95%,
zero fora de 0–120%) · FCO/lucro 10. Preço: DY 35 (4% → 10%) · EV/EBIT 25 (15 → 7) · P/L 20 (20 → 8) ·
P/VP 10 (2,5 → 1,0) · FCF yield 10 (2% → 10%).

**CÍCLICA** (aviso "setor cíclico") — Qualidade: ROE 5a 20 (8% → 20%) · ROIC 10 (6% → 16%) · margem 10 (3% → 12%) ·
Dív./EBITDA 30 (2,5 → 0,5) · liquidez corrente 10 (1,0 → 1,8) · CAGR receita 5 · payout 5 · FCO/lucro 10
(CAGR do lucro fora: as pontas de 5 anos caem em pontos diferentes do ciclo). Preço: P/L sobre o lucro médio de 5a 25
(15 → 6) · EV/EBIT sobre o EBIT médio de 5a 25 (12 → 5) · DY 30 (3% → 10%) · P/VP 20 (2,0 → 0,8).

### 5.5 Decisão
| Qualidade | Preço | Decisão |
|---|---|---|
| Falhou eliminatório | qualquer | **EVITAR** (nota final limitada a 30) |
| ≥ 70 | ≥ 60 | **COMPRAR** |
| ≥ 70 | < 60 | **AGUARDAR** (boa empresa, preço caro) |
| 50–69 | qualquer | **AGUARDAR** (observar) |
| < 50 | qualquer | **EVITAR** |

**Nota final exibida:** 0,6 × Qualidade + 0,4 × Preço (só ordenação; a decisão usa a tabela acima).
Desempate nas listas: nota final → Qualidade → liquidez.

### 5.6 Componente técnico (F8) — MM200 como referência de preço
Especificado pelo usuário em 13/10/2026. A **MM200 aritmética (simples) do gráfico diário** é usada como parâmetro de
**preço** (caro ou barato), não como sinal de entrada:
- Distância = preço ÷ MM200 − 1, com os fechamentos diários **ajustados por desdobramentos, grupamentos e
  bonificações** (como nos sites de gráficos).
- Nota técnica linear, travada nos limites: **10% ou mais abaixo da MM200 = 100**, **na MM200 = 50** ("ficar de olho"),
  **10% ou mais acima = 0**. São 5 pontos por 1% de distância (sem zona neutra).
- **Preço = 0,75 × Preço fundamentalista + 0,25 × nota técnica** (`technical.weight: 0.25`).
- Menos de 200 pregões de histórico → sem nota técnica (w = 0, o Preço usa só os fundamentos; nunca conta como N/A).
- A parte técnica nunca anula um eliminatório nem a trava de prejuízo (Preço ≤ 40 com LPA ≤ 0), aplicada depois da mistura.
- Só **ações**. FIIs, ETFs e BDRs: **sem regras por enquanto** (a MM200 para eles ainda será estudada).

Implementação: `app/rules/technical.py` (puro) e `rules.service.technical_for`. O histórico de ~6 anos é sincronizado
com o yfinance uma vez por dia por ticker (`sync_history`), reescrevendo o `close_adjusted` dos dias já em cache
(um desdobramento depois do cache muda o ajustado); o `close` bruto fica intacto para o livro. O gráfico de cotação
usa as mesmas barras ajustadas e desenha a MM200; a tela mostra o quadro "Análise gráfica — MM200" com a conta.

### 5.7 Saída obrigatória da análise
Para cada ativo pesquisado:
- Decisão.
- Nota final, nota de Qualidade e nota de Preço.
- Tabela com **todos os indicadores avaliados**: valor, faixa, pontos obtidos/possíveis e status ✅/⚠️/❌/➖.
- Eliminatórios com passou/falhou.
- Preço justo Graham, preço teto Bazin e preço atual, com o **cálculo passo a passo** (LPA = lucro TTM ÷ ações,
  VPA = patrimônio ÷ ações, √(22,5 × LPA × VPA); proventos por ação de cada ano, média ÷ 6%). A API manda as entradas
  em `valuation`.
- Um **"i"** ao lado de cada termo (indicadores, eliminatórios, notas, colunas) explica o que ele quer dizer ao passar o
  mouse (textos em `frontend/src/features/analise/glossary.ts`).
- Data-base dos dados (último DFP/ITR usado e data da cotação).

**Tela de Análise (14/10/2026, estilo Investidor10)**, nesta ordem:
1. Cabeçalho (preço, decisão, notas) e atalhos para as seções.
2. **Análise por regras** logo no início: Qualidade, Preço fundamentalista, MM200, eliminatórios, Graham e Bazin.
3. **Painel de indicadores** por tema: valuation, endividamento, eficiência, rentabilidade, crescimento e dividendos,
   tamanho e liquidez. Inclui indicadores só informativos (`app/fundamentals/indicators.py`, nenhuma regra os usa):
   DY 12m, EV/EBITDA, P/EBIT, P/Receita, P/Ativo, margens EBITDA/EBIT/líquida (12m), ROA, giro do ativo, dívida
   líquida/PL e /EBIT, passivo/ativo, valor da firma, receita/EBITDA/lucro 12m. Os que entram na nota mostram o status.
   Setor financeiro esconde os que não se aplicam (fluxo de caixa, EBIT, EBITDA, receita); os "médios 5a" de P/L, EV/EBIT
   e dívida só aparecem nas cíclicas.
4. Cotação (até 5 anos) com a MM200.
5. Gráficos anuais: receita e lucro; ROE e margens; proventos por ação e DY (cada medida no seu gráfico, um eixo só).
6. **Histórico de indicadores**, enxuto: só 10 razões (P/L, P/VP, DY, ROE, ROIC, margem líquida, dív./EBITDA, LPA,
   proventos por ação, payout) nos 5 últimos anos fechados + "12M". Padrão "Tendência" (valor mais recente, média 5a e
   minigráfico); "Tabela" mostra ano a ano. Valores em R$ ficam só nos gráficos.

A API manda `fundamentals` (todos os indicadores) e `history` (`YearFigures`: anos de DFP + 12M). Valores por ação
usam o número de ações atual; P/L, P/VP e DY dos anos passados usam o último fechamento de dezembro ajustado
(`fundamentals.service.year_end_prices` + `indicators.apply_year_prices`).

**Explicabilidade é requisito:** nenhuma decisão sem mostrar o porquê.

Guardar o histórico diário das decisões (`analysis_snapshots`) para detectar mudanças (usado pelas notificações).

### 5.8 Implementação (F6, `app/rules/`)
- `engine.py` é puro e não tem nenhum número próprio: tudo vem de `rules_config/stocks.yaml` (pesos, faixas,
  limites, tabela de decisão, classificação de setores, travas). `test_approved_weights_v2` trava os pesos aprovados.
- Nos setores, uma lista de chaves filtra as regras gerais; uma lista de regras (dicts) as substitui.
- Payout usa faixa "trapézio" (`band: [0, 0,25, 0,80, 1,0]`): 0 fora de 0–100%, ótimo entre 25–80%, linear entre.
- `Indicator.invalid` marca valor ausente por razão econômica (prejuízo, EBIT ≤ 0…); só vira 0 ponto onde a regra tem
  `if_invalid: zero`. `applies_to_template: BANK` aplica a regra só ao plano de contas de banco.
- Eliminatório sem dados (N/A) **não elimina** (aparece ➖); exceção: E3 com EBITDA ≤ 0 conta como reprovado.
  Com menos de 5 DFPs (mín. 3), o E1 tolera o mesmo número de anos com prejuízo (1).
- `evaluate(..., technical=nota)` combina a nota técnica (F8) quando habilitada no YAML; `analyze` calcula a nota.
- Motivo principal: eliminatório reprovado; senão, para COMPRAR o indicador que mais pontuou e para os demais o que
  mais perdeu pontos (mostrado na carteira, na Análise e usado no Discord). Indicadores de peso 0 nunca são o motivo.
- Snapshot diário por ticker (`analysis_snapshots`, 1 linha por ticker/dia, com a análise completa em JSON);
  `decision_changes(dia)` compara com o snapshot anterior. Gerado ao abrir a Análise, pelo botão "Atualizar preços"
  (cotações → eventos → reanálise da carteira) e pelo job `app.jobs.daily_analysis`.
- FIIs, ETFs e BDRs não são analisados (não estão no FCA da CVM).

---

## 6. Notificações diárias no Discord

> Versão inicial simples; será aprimorada depois com o usuário.

### 6.1 Canal
- Discord **Webhook** (criado pelo usuário no servidor dele). URL em `DISCORD_WEBHOOK_URL`.
- Envio via `Notifier` (interface) → `DiscordNotifier`. Respeitar limites do Discord (mensagem até 2.000 caracteres, embeds); dividir em várias mensagens se precisar.

### 6.2 Conteúdo do relatório diário
1. **Mudanças desde ontem:** ativos que mudaram de decisão (ex.: AGUARDAR → COMPRAR), no topo e em destaque.
2. **Ações da carteira por decisão:** 🟢 COMPRAR · 🟡 AGUARDAR · 🔴 EVITAR, cada uma com nota final, preço atual, distância da MM200 (ex.: `MM200 +3,9%`, quando há análise gráfica) e o principal motivo (indicador que mais pesou a favor ou contra).
3. **Proventos:** pagos hoje, datas-com nos próximos 5 dias úteis.
4. **Pendências:** bonificação sem custo, falha de fonte de dados, nota inconclusiva.
- FIIs/ETFs/BDRs aparecem só com preço e variação (sem decisão).
- Rodapé: data-base dos preços e dos fundamentos.

### 6.3 Execução (app local)
- Horário padrão: dias úteis, após o fechamento e depois do job de preços (ex.: 19h, horário de Brasília). Configurável.
- **Limitação:** o app roda local, então o envio só acontece se o computador estiver ligado. Por isso:
  - O relatório é um comando CLI independente (`python -m app.jobs.daily_report`) que pode ser agendado pelo **agendador do sistema operacional** (Agendador de Tarefas do Windows / cron), sem depender do backend aberto.
  - **Catch-up:** se o relatório do dia não foi enviado (computador desligado), envia na próxima execução, marcado como atrasado.
  - Registro de envios em banco para não mandar em duplicidade.
- Botão na UI: **"Enviar relatório agora"** (para teste).

### 6.4 Implementação (F7, `app/notifications/`)
- `report.py` monta o relatório (dados da carteira, último snapshot de cada ação, proventos, pendências) e o
  renderiza em Markdown do Discord; `discord.py` envia como texto simples (≤ 2.000 caracteres por mensagem,
  divididas por seção; menções desligadas; trata rate limit 429). Erros nunca mostram a URL do webhook.
- Mudanças de decisão são comparadas com as decisões gravadas no **último relatório agendado enviado**
  (`report_dispatches.decisions`), não com o snapshot de ontem: assim um dia sem envio não esconde mudanças.
  O primeiro relatório não tem comparação.
- "Pagos hoje" vira "Pagos desde dd/mm" quando houve dias sem relatório (janela máx. de 31 dias). Também mostra
  o total a receber já anunciado.
- Pendências também incluem ações sem análise e análises com mais de 3 dias.
- Agendamento: **Agendador de Tarefas do Windows** (`scripts/register_tasks.ps1`, usuário atual, sem admin):
  dias úteis às `REPORT_TIME` + ao entrar no Windows, com "executar assim que possível" se perdeu o horário.
  O job `daily_report` atualiza cotações → proventos → reanálise antes de enviar e só envia o que está devido:
  dia útil mais recente cujo horário já passou; enviado com mais de 2 h de atraso → marcado como atrasado.
  Vários dias perdidos → só o mais recente. Envio que falhou é tentado de novo na próxima execução.
- Sem APScheduler: o agendador do Windows já cobre o caso com o backend aberto; um advisory lock do Postgres
  impede dois envios simultâneos. Envio manual (botão/`--now`) fica registrado como `MANUAL` e não conta como o
  envio do dia.
- Webhook não configurado: o job sai sem atualizar nem enviar (registra aviso no log).

---

## 7. Fases

| Fase | Entrega |
|---|---|
| **F0** | Setup: repo GitHub privado `carteira-b3`, PostgreSQL 16 nativo + uv, FastAPI + Alembic, frontend Vite + shadcn, README |
| **F1** | Motor de carteira: models, **lançamento manual (individual e em lote)**, PM, eventos manuais — **com testes numéricos** |
| **F2** | Preços (yfinance + cache), CDI (BCB), painel completo da carteira |
| **F3** | Proventos e eventos corporativos automáticos (seção 3.9), agenda de proventos, pendências |
| **F4** | Importador B3 (Negociação + Movimentação) com prévia, deduplicação e conciliação de proventos |
| **F5** | Ingestão CVM, mapeamento ticker↔CNPJ, cálculo dos indicadores |
| **F6** | Motor de regras (YAML), tela de pesquisa/análise de ativo, nota na carteira, histórico de decisões |
| **F7** | Relatório diário no Discord |
| **F8** | **Análise gráfica**: MM200 diária como referência de preço, peso 0,25 na nota de Preço (seção 5.6) |

---

## 8. Radar (não implementar sem pedido explícito)
- Editor de pesos na UI (os pesos v2 foram definidos em 10/10/2026).
- **Backtest** das regras com dados históricos da CVM (atenção a overfitting).
- Regras para FIIs (P/VP, DY, vacância — dados de informes da CVM).
- Aprimoramentos das notificações (alertas intradiários, watchlist fora da carteira, preço-alvo).
- Watchlist.
- Pluggy como fonte automática de posição.
- Renda fixa / Tesouro.
- IR: apuração mensal, DARF, isenção de R$ 20 mil.
- Importação de notas de corretagem (PDF) para custos exatos.

## 9. Decisões pendentes do usuário
- [x] Exemplos reais dos extratos B3 recebidos e layout documentado (originais não vão para o git).
- [x] Criar o **webhook do Discord** e colocar a URL no `.env`.
- [x] Pesos das regras (seção 5, v2 aprovada em 10/10/2026; revisão em 30/04/2027).
- [x] Especificação da análise gráfica (F8, MM200 — 13/10/2026).
- [x] Liquidez diária fora dos eliminatórios (14/10/2026, regras v4).
- [ ] Análise gráfica para FIIs, ETFs e BDRs (a estudar).
