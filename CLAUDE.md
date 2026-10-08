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
cd backend && uv run python -m app.jobs.daily_report   # (F7) relatório diário manual
cd frontend && npm run dev                         # UI em http://localhost:5180 (proxy /api → :8000)
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
- Setor especial: FINANCIAL (modelo de banco ou setor CVM de bancos/seguradoras/intermediação financeira,
  inclusive holdings desses setores) e UTILITY (energia elétrica, saneamento, água e gás).
- Ativos da carteira que são ações listadas recebem o setor da CVM e a classe STOCK (corrige units "11").

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
| EV/EBIT | (Valor de mercado + dívida líquida) / EBIT TTM |
| Valor de mercado | Σ (ações de cada classe, excluindo tesouraria × preço da classe) |
| Preço justo Graham | √(22,5 × LPA × VPA). LPA ou VPA ≤ 0 → N/A |
| Margem de segurança Graham | (preço justo − preço) / preço |
| DY médio 5a | Proventos brutos por ação médios dos últimos 5 anos / preço atual |
| Preço teto Bazin | Proventos por ação médios 5a / 0,06 (exibir na tela) |
| Liquidez diária | Média do volume financeiro (preço × volume) dos últimos 2 meses |

---

## 5. Motor de Regras — ⚠️ REGRAS EM AVALIAÇÃO

> **Estado atual: TODOS OS PESOS SÃO IGUAIS.** O usuário vai avaliar mais à frente quais indicadores pesam mais e decidir os pesos. **Não alterar pesos, faixas ou limites sem decisão explícita do usuário.**
> A implementação lê tudo de `rules_config/stocks.yaml`. Qualquer mudança aprovada deve ser feita no YAML **e** nesta seção.
> A análise gráfica (F8) vai entrar como componente adicional da nota de Preço, com peso próprio.

### 5.1 Pontuação gradual
- Cada indicador tem faixa **"ruim"** e **"ótimo"**. Pontuação = interpolação linear entre as duas, limitada a [0, 1], × peso.
- Nota = soma dos pontos obtidos / soma dos pesos avaliados × 100.
- Status exibido: ✅ ≥ 70% dos pontos · ⚠️ 30–70% · ❌ < 30% · ➖ sem dados.
- **Indicador sem dados (N/A)** sai do denominador e aparece como "sem dados". Se mais de 30% do peso de uma nota estiver N/A → nota marcada **"inconclusiva"** e decisão = AGUARDAR.

### 5.2 Camada 1 — Eliminatórios (falhou em qualquer um → EVITAR)
| ID | Regra | Limite |
|---|---|---|
| E1 | Lucro líquido positivo nos últimos 5 anos | ≥ 4 de 5 anos |
| E2 | Patrimônio líquido | > 0 |
| E3 | Dívida líquida / EBITDA | ≤ 3,5 (utilities: ≤ 4,5) |
| E4 | Liquidez média diária | ≥ R$ 2 milhões |

### 5.3 Camada 2 — Nota de Qualidade (0–100) — pesos iguais
| Indicador | Ruim → Ótimo | Peso |
|---|---|---|
| ROE médio 5a | 8% → 20% | 12,5 |
| ROIC | 6% → 15% | 12,5 |
| Margem líquida média | 5% → 15% | 12,5 |
| CAGR lucro 5a | 0% → 12% | 12,5 |
| Dívida líquida / EBITDA | 3,0 → 0,5 (caixa líquido = ótimo) | 12,5 |
| CAGR receita 5a | 0% → 10% | 12,5 |
| Liquidez corrente | 0,8 → 1,5 | 12,5 |
| Payout médio | ótimo dentro de 25–80%; zero fora de 0–100% | 12,5 |

### 5.4 Camada 3 — Nota de Preço (0–100) — pesos iguais
| Indicador | Ruim → Ótimo | Peso |
|---|---|---|
| Margem de segurança Graham | −20% → +30% | 20 |
| P/L | 25 → 8 | 20 |
| EV/EBIT | 15 → 6 | 20 |
| DY médio 5a | 2% → 8% | 20 |
| P/VP | 3,0 → 1,0 | 20 |

### 5.5 Decisão
| Qualidade | Preço | Decisão |
|---|---|---|
| Falhou eliminatório | qualquer | **EVITAR** |
| ≥ 70 | ≥ 60 | **COMPRAR** |
| ≥ 70 | < 60 | **AGUARDAR** (boa empresa, preço caro) |
| 50–69 | qualquer | **AGUARDAR** (observar) |
| < 50 | qualquer | **EVITAR** |

**Nota final exibida:** 0,5 × Qualidade + 0,5 × Preço (peso igual; em avaliação).

### 5.6 Setores com regras especiais
- **Bancos e seguradoras:** não usar EBITDA, dívida líquida, ROIC, EV/EBIT nem liquidez corrente. Conjunto reduzido, com pesos iguais:
  - Qualidade: ROE, CAGR lucro, payout.
  - Preço: P/L, P/VP, DY.
  - Eliminatórios: E1, E2, E4.
  - Exibir aviso **"análise parcial — setor financeiro"**.
- **Utilities** (energia, saneamento): E3 com limite 4,5.
- FIIs, ETFs e BDRs: **sem regras por enquanto** (só aparecem na carteira).

### 5.7 Saída obrigatória da análise
Para cada ativo pesquisado:
- Decisão.
- Nota final, nota de Qualidade e nota de Preço.
- Tabela com **todos os indicadores avaliados**: valor, faixa, pontos obtidos/possíveis e status ✅/⚠️/❌/➖.
- Eliminatórios com passou/falhou.
- Preço justo Graham, preço teto Bazin e preço atual.
- Data-base dos dados (último DFP/ITR usado e data da cotação).

**Explicabilidade é requisito:** nenhuma decisão sem mostrar o porquê.

Guardar o histórico diário das decisões (`analysis_snapshots`) para detectar mudanças (usado pelas notificações).

---

## 6. Notificações diárias no Discord

> Versão inicial simples; será aprimorada depois com o usuário.

### 6.1 Canal
- Discord **Webhook** (criado pelo usuário no servidor dele). URL em `DISCORD_WEBHOOK_URL`.
- Envio via `Notifier` (interface) → `DiscordNotifier`. Respeitar limites do Discord (mensagem até 2.000 caracteres, embeds); dividir em várias mensagens se precisar.

### 6.2 Conteúdo do relatório diário
1. **Mudanças desde ontem:** ativos que mudaram de decisão (ex.: AGUARDAR → COMPRAR), no topo e em destaque.
2. **Ações da carteira por decisão:** 🟢 COMPRAR · 🟡 AGUARDAR · 🔴 EVITAR, cada uma com nota final, preço atual e o principal motivo (indicador que mais pesou a favor ou contra).
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
| **F8** | **Análise gráfica** (especificação será feita pelo usuário antes de começar) |

---

## 8. Radar (não implementar sem pedido explícito)
- **Definição dos pesos** pelo usuário (hoje todos iguais) e editor de pesos na UI.
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
- [ ] Criar o **webhook do Discord** e colocar a URL no `.env`.
- [ ] Pesos definitivos das regras (seção 5).
- [ ] Especificação da análise gráfica (F8).
