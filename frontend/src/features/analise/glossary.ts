/** Plain-language explanations shown by the "i" next to each term on the analysis page. */

export interface Term {
  title: string;
  text: string;
}

/** Indicators, by the key the backend sends. */
export const INDICATOR_TERMS: Record<string, Term> = {
  roe: {
    title: "ROE (retorno sobre o patrimônio)",
    text: "Quanto a empresa lucrou nos últimos 12 meses para cada R$ 100 de patrimônio dos acionistas. Lucro ÷ patrimônio médio.",
  },
  roe_5y: {
    title: "ROE médio de 5 anos",
    text: "Retorno sobre o patrimônio: quanto a empresa lucra para cada R$ 100 do capital dos acionistas. Média dos últimos 5 anos (lucro do ano ÷ patrimônio médio do ano). Quanto maior, melhor; acima de 15–20% é excelente.",
  },
  roic: {
    title: "ROIC (retorno sobre o capital investido)",
    text: "Quanto o negócio rende sobre todo o capital que usa (dos acionistas e da dívida). EBIT dos últimos 12 meses × (1 − 34% de imposto) ÷ (patrimônio + dívida bruta − caixa). Mostra se a empresa ganha mais do que custa o dinheiro dela.",
  },
  net_margin_5y: {
    title: "Margem líquida média de 5 anos",
    text: "Quanto sobra de lucro para cada R$ 100 vendidos. Lucro líquido ÷ receita líquida, média dos últimos 5 anos.",
  },
  net_debt_ebitda: {
    title: "Dívida líquida / EBITDA",
    text: "Quantos anos de geração de caixa operacional (EBITDA) a empresa levaria para quitar a dívida líquida (empréstimos, financiamentos e debêntures menos caixa). Abaixo de 1 é confortável; acima de 3 preocupa. Arrendamentos (IFRS 16) não entram. EBITDA negativo vale 0 ponto.",
  },
  net_debt_ebitda_norm: {
    title: "Dívida líquida / EBITDA médio de 5 anos",
    text: "A mesma conta da dívida líquida / EBITDA, mas sobre o EBITDA médio de 5 anos. Usada em setores cíclicos, para o endividamento não parecer baixo só porque o ano foi de pico.",
  },
  current_ratio: {
    title: "Liquidez corrente",
    text: "Ativo circulante ÷ passivo circulante: quanto a empresa tem em caixa e a receber em até 12 meses para cada R$ 1 que deve no mesmo prazo. Abaixo de 1 indica aperto no curto prazo.",
  },
  cagr_revenue_5y: {
    title: "CAGR da receita em 5 anos",
    text: "Crescimento médio anual composto da receita nos últimos 5 anos (balanços anuais). Se a receita do início era zero ou negativa, fica sem dados.",
  },
  cagr_earnings_5y: {
    title: "CAGR do lucro em 5 anos",
    text: "Crescimento médio anual composto do lucro nos últimos 5 anos. Lucro inicial ≤ 0 deixa sem dados; lucro final ≤ 0 (piorou para prejuízo) vale 0 ponto.",
  },
  cagr_book_5y: {
    title: "CAGR do patrimônio em 5 anos",
    text: "Crescimento médio anual do patrimônio dos acionistas nos últimos 5 anos. Em bancos e seguradoras, mostra se o lucro está sendo retido e multiplicado.",
  },
  cash_conversion_5y: {
    title: "FCO / lucro de 5 anos",
    text: "Quanto do lucro contábil virou caixa de verdade: soma do fluxo de caixa operacional ÷ soma do lucro líquido dos últimos 5 anos. Perto de 1 ou acima é saudável; muito abaixo pode indicar lucro que não vira dinheiro.",
  },
  earnings_drops_5y: {
    title: "Quedas de lucro acima de 25% em 5 anos",
    text: "Em quantos dos últimos 5 anos o lucro ficou abaixo de 75% do ano anterior (ou virou prejuízo). Mede a estabilidade do lucro: 0 é o ideal.",
  },
  payout_5y: {
    title: "Payout médio de 5 anos",
    text: "Parte do lucro distribuída como dividendos e JCP, média de 5 anos. A faixa ideal aparece ao lado: abaixo dela a empresa quase não remunera o acionista; acima de 100% distribui mais do que lucra. Sem nenhum ano de lucro vale 0 ponto.",
  },
  equity_to_assets: {
    title: "PL / ativo total (bancos)",
    text: "Patrimônio ÷ ativo total. É o colchão de capital próprio do banco: quanto maior, menos alavancado e mais seguro.",
  },
  pe: {
    title: "P/L (preço / lucro)",
    text: "Preço da ação ÷ lucro por ação (LPA) dos últimos 12 meses. Em quantos anos o lucro atual “pagaria” o preço. Quanto menor, mais barato. Com prejuízo (LPA ≤ 0) vale 0 ponto.",
  },
  pe_norm: {
    title: "P/L sobre o lucro médio de 5 anos",
    text: "Preço ÷ lucro por ação médio dos últimos 5 anos. Usado em setores cíclicos: no pico do ciclo o P/L normal parece barato, e no vale parece caro.",
  },
  pb: {
    title: "P/VP (preço / valor patrimonial)",
    text: "Preço da ação ÷ valor patrimonial por ação (VPA). Abaixo de 1, a bolsa paga menos do que o patrimônio contábil da empresa.",
  },
  ev_ebit: {
    title: "EV/EBIT",
    text: "Valor da firma (valor de mercado + dívida líquida + participação dos minoritários) ÷ lucro operacional (EBIT) dos últimos 12 meses. Parecido com o P/L, mas considera a dívida. Quanto menor, mais barato. EBIT ≤ 0 vale 0 ponto.",
  },
  ev_ebit_norm: {
    title: "EV/EBIT sobre o EBIT médio de 5 anos",
    text: "Valor da firma ÷ EBIT médio dos últimos 5 anos. Usado em setores cíclicos, pelo mesmo motivo do P/L médio.",
  },
  dy_5y: {
    title: "DY médio de 5 anos (dividend yield)",
    text: "Proventos (dividendos + JCP) pagos por ação, média dos últimos 5 anos, ÷ preço atual. É quanto você receberia por ano em proventos, em %, comprando hoje, se a empresa pagar como pagou.",
  },
  fcf_yield: {
    title: "FCF yield (rendimento do caixa livre)",
    text: "Caixa livre dos últimos 12 meses (caixa operacional − investimentos em imobilizado e intangível) ÷ valor de mercado. Quanto sobra de caixa por ano para cada R$ 100 que a empresa vale na bolsa.",
  },
  graham_margin: {
    title: "Margem de segurança de Graham",
    text: "Distância entre o preço justo de Graham e o preço atual. Positiva = ação abaixo do preço justo. Só exibida: não entra na nota, porque repete o P/L e o P/VP.",
  },
  // Display-only indicators (indicator panel)
  dy_12m: {
    title: "DY dos últimos 12 meses",
    text: "Dividendos + JCP pagos nos últimos 12 meses (fluxo de caixa da CVM) por ação ÷ preço atual. Mostra o que a ação rendeu em proventos no último ano; a nota usa a média de 5 anos, mais estável.",
  },
  dps_12m: {
    title: "Proventos por ação (12 meses)",
    text: "Dividendos + JCP pagos nos últimos 12 meses ÷ número de ações atual.",
  },
  eps: {
    title: "LPA (lucro por ação)",
    text: "Lucro dos últimos 12 meses atribuído aos controladores ÷ número de ações (sem as de tesouraria).",
  },
  bvps: {
    title: "VPA (valor patrimonial por ação)",
    text: "Patrimônio líquido dos controladores no último balanço ÷ número de ações (sem as de tesouraria).",
  },
  ev_ebitda: {
    title: "EV/EBITDA",
    text: "Valor da firma ÷ EBITDA dos últimos 12 meses. Como o EV/EBIT, mas soma de volta a depreciação: bom para comparar empresas com muitos ativos físicos. Quanto menor, mais barato.",
  },
  p_ebit: {
    title: "P/EBIT",
    text: "Valor de mercado ÷ lucro operacional (EBIT) dos últimos 12 meses. Parecido com o P/L, mas antes de juros e impostos.",
  },
  psr: {
    title: "P/Receita (PSR)",
    text: "Valor de mercado ÷ receita líquida dos últimos 12 meses. Útil quando o lucro está deprimido; compare só com empresas do mesmo setor (as margens mudam muito).",
  },
  p_assets: {
    title: "P/Ativo",
    text: "Valor de mercado ÷ ativo total do último balanço: quanto a bolsa paga por cada R$ 1 de ativos da empresa.",
  },
  net_margin: {
    title: "Margem líquida (12 meses)",
    text: "Lucro líquido ÷ receita líquida dos últimos 12 meses. A nota usa a média de 5 anos.",
  },
  ebit_margin: {
    title: "Margem EBIT",
    text: "Lucro operacional (EBIT) ÷ receita líquida dos últimos 12 meses: quanto sobra da operação antes de juros e impostos.",
  },
  ebitda_margin: {
    title: "Margem EBITDA",
    text: "EBITDA ÷ receita líquida dos últimos 12 meses: a geração de caixa da operação para cada R$ 100 vendidos.",
  },
  roa: {
    title: "ROA (retorno sobre o ativo)",
    text: "Lucro dos últimos 12 meses ÷ ativo total. Mostra quanto a empresa lucra com tudo o que tem, independente de como se financia.",
  },
  asset_turnover: {
    title: "Giro do ativo",
    text: "Receita dos últimos 12 meses ÷ ativo total: quantas vezes por ano a empresa “gira” os ativos em vendas.",
  },
  net_debt_equity: {
    title: "Dívida líquida / patrimônio",
    text: "Dívida líquida (empréstimos e debêntures − caixa) ÷ patrimônio dos controladores. Negativo = mais caixa do que dívida.",
  },
  net_debt_ebit: {
    title: "Dívida líquida / EBIT",
    text: "Quantos anos de lucro operacional (EBIT) seriam necessários para pagar a dívida líquida.",
  },
  liabilities_assets: {
    title: "Passivo / ativo",
    text: "Parte dos ativos financiada por terceiros (tudo o que a empresa deve, não só dívida bancária) ÷ ativo total.",
  },
  market_cap: {
    title: "Valor de mercado",
    text: "Quanto a bolsa paga pela empresa inteira hoje: ações de cada classe (sem tesouraria) × o preço da classe.",
  },
  ev: {
    title: "Valor da firma (EV)",
    text: "Valor de mercado + dívida líquida + participação dos minoritários: o preço para comprar o negócio inteiro, assumindo a dívida.",
  },
  net_debt: {
    title: "Dívida líquida",
    text: "Empréstimos, financiamentos e debêntures (curto e longo prazo) − caixa e aplicações. Arrendamentos (IFRS 16) não entram. Negativa = caixa líquido.",
  },
  revenue_ttm: {
    title: "Receita líquida (12 meses)",
    text: "Soma da receita dos últimos 4 trimestres (balanços da CVM).",
  },
  ebitda_ttm: {
    title: "EBITDA (12 meses)",
    text: "Lucro operacional (EBIT) + depreciação e amortização dos últimos 4 trimestres. Aproxima o caixa gerado pela operação.",
  },
  net_income_ttm: {
    title: "Lucro líquido (12 meses)",
    text: "Lucro atribuído aos controladores nos últimos 4 trimestres.",
  },
  daily_liquidity: {
    title: "Liquidez média diária",
    text: "Volume financeiro médio negociado por dia nos últimos 2 meses. Só informativo (não elimina mais a ação): liquidez baixa dificulta comprar ou vender sem mexer no preço.",
  },
  dps_5y: {
    title: "Proventos por ação médios de 5 anos",
    text: "Média dos dividendos + JCP pagos por ação nos últimos 5 anos. É a base do DY médio e do preço teto de Bazin.",
  },
};

/** Eliminatory rules, by id. */
export const ELIMINATORY_TERMS: Record<string, string> = {
  E1: "A empresa precisa ter dado lucro em pelo menos 4 dos últimos 5 anos. Prejuízo recorrente elimina.",
  E2: "Patrimônio líquido negativo significa que a empresa deve mais do que tem. Elimina.",
  E3: "Dívida líquida acima do limite em relação ao EBITDA indica endividamento perigoso (geral 3,5; utilities 4,5; cíclicas 3,0 sobre o EBITDA médio de 5 anos). EBITDA negativo também elimina.",
  E5: "Empresa em recuperação judicial ou extrajudicial, falência, liquidação ou com atividades paralisadas é eliminada (cadastro da CVM e lista manual).",
};

/** Other terms on the page. */
export const TERMS = {
  decision: {
    title: "Decisão",
    text: "Comprar: qualidade ≥ 70 e preço ≥ 60. Aguardar: boa empresa cara (qualidade ≥ 70 e preço < 60), qualidade entre 50 e 69 ou nota inconclusiva. Evitar: qualidade abaixo de 50 ou algum eliminatório reprovado.",
  },
  final: {
    title: "Nota final",
    text: "0,6 × Qualidade + 0,4 × Preço, de 0 a 100. Serve para ordenar as ações; a decisão segue a regra de qualidade e preço. Com eliminatório reprovado fica limitada a 30.",
  },
  quality: {
    title: "Nota de Qualidade",
    text: "De 0 a 100: o quanto o negócio é bom (rentabilidade, endividamento, crescimento, geração de caixa e estabilidade), independente do preço da ação.",
  },
  price: {
    title: "Nota de Preço",
    text: "De 0 a 100: o quanto a ação está barata. 75% vem dos fundamentos (múltiplos, dividendos e caixa livre) e 25% da posição do preço em relação à MM200 (análise gráfica). Com prejuízo nos últimos 12 meses fica limitada a 40.",
  },
  range: {
    title: "Faixa ruim → ótimo",
    text: "No valor ruim (ou pior) o indicador vale 0 ponto; no ótimo (ou melhor), todos os pontos; entre os dois, proporcional.",
  },
  points: {
    title: "Pontos",
    text: "Pontos obtidos / peso do indicador. A nota é a soma dos pontos ÷ soma dos pesos avaliados × 100. Indicador sem dados sai da conta; se mais de 30% do peso ficar sem dados, a nota é inconclusiva.",
  },
  status: {
    title: "Status",
    text: "Bom: 70% ou mais dos pontos. Médio: de 30% a 70%. Ruim: menos de 30%. Sem dados: não foi possível calcular (não conta na nota).",
  },
  eliminatory: {
    title: "Eliminatórios",
    text: "Filtros de segurança aplicados antes das notas. Reprovar em qualquer um leva a Evitar, mesmo com notas boas. Sem dados não elimina.",
  },
  graham: {
    title: "Preço justo de Graham",
    text: "Fórmula de Benjamin Graham: √(22,5 × LPA × VPA). O 22,5 vem de um P/L máximo de 15 × P/VP máximo de 1,5. Faz sentido para empresas lucrativas e estáveis; com LPA ou VPA ≤ 0 não se aplica.",
  },
  bazin: {
    title: "Preço teto de Bazin",
    text: "Método de Décio Bazin: o preço máximo para que os proventos rendam pelo menos 6% ao ano. Proventos por ação médios de 5 anos ÷ 6%. Acima desse preço, o dividendo rende menos de 6%.",
  },
  technical: {
    title: "Análise gráfica (MM200)",
    text: "Compara o preço com a média dos fechamentos dos últimos 200 pregões (gráfico diário). A média é a referência de preço: acima dela a ação está cara, na média é para ficar de olho e abaixo está barata. 10% ou mais abaixo = nota 100; na média = 50; 10% ou mais acima = 0, em linha reta (5 pontos por 1%). Entra com peso de 25% na nota de Preço.",
  },
  sma: {
    title: "MM200 (média móvel de 200 dias)",
    text: "Média aritmética simples dos últimos 200 fechamentos diários (cerca de 10 meses de pregão), ajustados por desdobramentos, grupamentos e bonificações, como nos sites de gráficos.",
  },
  distance: {
    title: "Distância da MM200",
    text: "Quanto o preço atual está acima (+) ou abaixo (−) da MM200: preço ÷ MM200 − 1.",
  },
  fundamentalPrice: {
    title: "Preço — fundamentalista",
    text: "Parte da nota de Preço que vem dos indicadores fundamentalistas (múltiplos, dividendos e caixa livre). Ela pesa 75% na nota de Preço; os outros 25% vêm da análise gráfica (MM200).",
  },
  eps: {
    title: "LPA (lucro por ação)",
    text: "Lucro dos últimos 12 meses atribuído aos controladores ÷ número de ações (sem as de tesouraria).",
  },
  bvps: {
    title: "VPA (valor patrimonial por ação)",
    text: "Patrimônio líquido dos controladores no último balanço ÷ número de ações (sem as de tesouraria).",
  },
  dps: {
    title: "Proventos por ação",
    text: "Dividendos + JCP pagos no ano (fluxo de caixa da controladora, CVM) ÷ número de ações atual.",
  },
  panel: {
    title: "Indicadores fundamentalistas",
    text: "Todos os indicadores calculados com os balanços da CVM e a cotação atual. Os que entram na nota mostram o status (bom, médio ou ruim) pela faixa da regra; os demais são só informativos.",
  },
  history: {
    title: "Histórico de indicadores",
    text: "Os principais indicadores nos 5 últimos anos fiscais (balanço anual, DFP) e nos últimos 12 meses: o valor mais recente, a média de 5 anos e a tendência. Em “Tabela”, o valor de cada ano. Anos anteriores usam o fechamento de dezembro, ajustado por desdobramentos, e o número de ações atual.",
  },
  ttm: {
    title: "12M — últimos 12 meses",
    text: "Soma dos últimos 4 trimestres (último ITR + último balanço anual − o mesmo período do ano anterior), com o preço atual.",
  },
  avg5y: {
    title: "Média de 5 anos",
    text: "Média simples dos 5 últimos anos fechados. É a base dos indicadores “médios 5a” usados nas notas (ROE, margem, payout, DY).",
  },
  rules: {
    title: "Análise por regras",
    text: "As notas de Qualidade e de Preço pontuam cada indicador entre uma faixa ruim e uma ótima. A qualidade usa médias e crescimento de 5 anos (ROE, margem, payout, FCO/lucro, CAGR); o preço usa os múltiplos atuais, o DY médio de 5 anos e a MM200.",
  },
} satisfies Record<string, Term>;
