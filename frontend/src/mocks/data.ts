/**
 * FICTITIOUS demo portfolio — invented numbers used until the backend endpoints exist.
 * Deterministic (seeded) so screenshots and tests are stable.
 */
import type {
  AssetAnalysis,
  AssetClass,
  AssetSearchResult,
  Decision,
  Dividend,
  DividendType,
  EliminatoryCheck,
  EquityPoint,
  ImportPreview,
  ImportPreviewRow,
  Indicator,
  PendingItem,
  PortfolioSummary,
  Position,
  PriceBar,
  ReturnPoint,
  RulesSnapshot,
  Transaction,
} from "@/api/types";
import { formatMultiple, formatPct } from "@/lib/format";

export const TODAY = "2026-10-08";

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

const d2 = (n: number) => n.toFixed(2);
const d4 = (n: number) => n.toFixed(4);

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function isWeekday(iso: string): boolean {
  const day = new Date(`${iso}T12:00:00Z`).getUTCDay();
  return day !== 0 && day !== 6;
}

interface Holding {
  ticker: string;
  name: string;
  asset_class: AssetClass;
  sector: string;
  quantity: number;
  avg: number;
  price: number;
  prev: number;
  dividendsReceived: number;
  pendingCost?: boolean;
}

export const HOLDINGS: Holding[] = [
  { ticker: "WEGE3", name: "WEG S.A.", asset_class: "STOCK", sector: "Bens industriais", quantity: 120, avg: 38.42, price: 52.1, prev: 51.46, dividendsReceived: 182.4 },
  { ticker: "ITUB4", name: "Itaú Unibanco", asset_class: "STOCK", sector: "Financeiro", quantity: 330, avg: 27.91, price: 36.45, prev: 36.02, dividendsReceived: 1288.3, pendingCost: true },
  { ticker: "PETR4", name: "Petrobras", asset_class: "STOCK", sector: "Petróleo e gás", quantity: 200, avg: 31.2, price: 34.8, prev: 35.31, dividendsReceived: 1915.6 },
  { ticker: "VALE3", name: "Vale", asset_class: "STOCK", sector: "Mineração", quantity: 90, avg: 68.5, price: 57.2, prev: 56.88, dividendsReceived: 702.9 },
  { ticker: "EGIE3", name: "Engie Brasil", asset_class: "STOCK", sector: "Energia elétrica", quantity: 150, avg: 41.1, price: 43.9, prev: 43.75, dividendsReceived: 644.1 },
  { ticker: "KLBN11", name: "Klabin", asset_class: "STOCK", sector: "Papel e celulose", quantity: 250, avg: 19.8, price: 21.1, prev: 21.32, dividendsReceived: 301.5 },
  { ticker: "RADL3", name: "Raia Drogasil", asset_class: "STOCK", sector: "Saúde", quantity: 60, avg: 26.4, price: 22.9, prev: 23.1, dividendsReceived: 38.2 },
  { ticker: "HGLG11", name: "CSHG Logística", asset_class: "FII", sector: "Logística", quantity: 25, avg: 158.3, price: 162.4, prev: 162.05, dividendsReceived: 551.0 },
  { ticker: "KNRI11", name: "Kinea Renda Imobiliária", asset_class: "FII", sector: "Híbrido", quantity: 40, avg: 142.0, price: 150.2, prev: 149.6, dividendsReceived: 702.4 },
  { ticker: "BOVA11", name: "iShares Ibovespa", asset_class: "ETF", sector: "Índice Brasil", quantity: 30, avg: 112.4, price: 131.8, prev: 131.2, dividendsReceived: 0 },
  { ticker: "IVVB11", name: "iShares S&P 500", asset_class: "ETF", sector: "Índice EUA", quantity: 15, avg: 280.0, price: 352.1, prev: 349.7, dividendsReceived: 0 },
  { ticker: "AAPL34", name: "Apple (BDR)", asset_class: "BDR", sector: "Tecnologia", quantity: 40, avg: 48.0, price: 61.3, prev: 61.95, dividendsReceived: 22.8 },
];

const REALIZED_PNL = 1384.27;
const DIVIDENDS_RECEIVABLE = 236.48;

export function buildPositions(): Position[] {
  const total = HOLDINGS.reduce((acc, h) => acc + h.quantity * h.price, 0);
  return HOLDINGS.map((h) => {
    const value = h.quantity * h.price;
    const cost = h.quantity * h.avg;
    return {
      ticker: h.ticker,
      name: h.name,
      asset_class: h.asset_class,
      sector: h.sector,
      quantity: String(h.quantity),
      avg_price: d4(h.avg),
      last_price: d2(h.price),
      price_date: "2026-10-07",
      day_change_pct: d2(((h.price - h.prev) / h.prev) * 100),
      market_value: d2(value),
      cost_basis: d2(cost),
      weight_pct: d2((value / total) * 100),
      pnl: d2(value - cost),
      pnl_pct: d2(((value - cost) / cost) * 100),
      dividends_received: d2(h.dividendsReceived),
      yield_on_cost_pct: h.dividendsReceived ? d2((h.dividendsReceived / 2.6 / cost) * 100) : null,
      pending_cost: Boolean(h.pendingCost),
      rules: rulesFromAnalysis(h.ticker),
    };
  });
}

export function buildSummary(): PortfolioSummary {
  const equity = HOLDINGS.reduce((a, h) => a + h.quantity * h.price, 0);
  const invested = HOLDINGS.reduce((a, h) => a + h.quantity * h.avg, 0);
  const prev = HOLDINGS.reduce((a, h) => a + h.quantity * h.prev, 0);
  const dividendsTotal = HOLDINGS.reduce((a, h) => a + h.dividendsReceived, 0);
  return {
    as_of: TODAY,
    prices_as_of: "2026-10-07T18:12:00-03:00",
    equity: d2(equity),
    invested: d2(invested),
    unrealized_pnl: d2(equity - invested),
    realized_pnl: d2(REALIZED_PNL),
    total_return_pct: "21.84",
    return_12m_pct: "13.62",
    day_change: d2(equity - prev),
    day_change_pct: d2(((equity - prev) / prev) * 100),
    dividends_12m: "2843.17",
    dividends_total: d2(dividendsTotal),
    dividends_receivable: d2(DIVIDENDS_RECEIVABLE),
    warnings: [],
  };
}

export function buildPending(): PendingItem[] {
  return [
    {
      id: "p1",
      kind: "BONUS_NO_COST",
      ticker: "ITUB4",
      date: "2026-09-22",
      message: "Bonificação de 30 ações sem custo atribuído. O preço médio está provisório.",
      transaction_id: 9001,
    },
    {
      id: "p2",
      kind: "POSSIBLE_DUPLICATE",
      ticker: "PETR4",
      date: "2026-08-14",
      message: "Compra manual de 50 ações parecida com uma linha importada da B3.",
      transaction_id: 9002,
    },
  ];
}

/** Weekly equity vs invested since Jan 2023, ending at today's totals. */
export function buildEquitySeries(): EquityPoint[] {
  const summary = buildSummary();
  const finalEquity = Number(summary.equity);
  const finalInvested = Number(summary.invested);
  const rand = rng(7);
  const points: { date: string; invested: number; factor: number }[] = [];
  let date = "2023-01-06";
  let invested = 4200;
  let factor = 1;
  const contributionWeeks = 196;
  let week = 0;
  while (date <= TODAY) {
    if (week > 0 && week % 4 === 0) invested += (finalInvested - 4200) / (contributionWeeks / 4);
    factor *= 1 + (rand() - 0.47) * 0.035;
    points.push({ date, invested: Math.min(invested, finalInvested), factor });
    date = addDays(date, 7);
    week++;
  }
  const last = points[points.length - 1];
  const targetFactor = finalEquity / finalInvested;
  return points.map((p, i) => {
    const t = i / (points.length - 1);
    // Blend the random walk so the series lands exactly on today's equity.
    const f = p.factor * Math.pow(targetFactor / last.factor, t);
    const inv = i === points.length - 1 ? finalInvested : p.invested;
    return { date: i === points.length - 1 ? TODAY : p.date, equity: d2(inv * f), invested: d2(inv) };
  });
}

/** Weekly cumulative returns (portfolio TWR, IBOV, CDI) since Jan 2023. */
export function buildReturnSeries(): ReturnPoint[] {
  const rand = rng(11);
  const out: ReturnPoint[] = [];
  let date = "2023-01-06";
  let port = 0;
  let ibov = 0;
  let cdi = 0;
  while (date <= TODAY) {
    port = (1 + port / 100) * (1 + (rand() - 0.46) * 0.032) * 100 - 100;
    ibov = (1 + ibov / 100) * (1 + (rand() - 0.475) * 0.03) * 100 - 100;
    cdi = (1 + cdi / 100) * 1.0022 * 100 - 100;
    out.push({ date, portfolio_pct: d2(port), ibov_pct: d2(ibov), cdi_pct: d2(cdi) });
    date = addDays(date, 7);
  }
  // Tilt the random walk so the portfolio ends at the summary's total return.
  const target = 1 + Number(buildSummary().total_return_pct) / 100;
  const last = 1 + Number(out[out.length - 1].portfolio_pct) / 100;
  return out.map((p, i) => {
    const t = i / (out.length - 1);
    const tilted = (1 + Number(p.portfolio_pct) / 100) * Math.pow(target / last, t);
    return { ...p, portfolio_pct: d2((tilted - 1) * 100) };
  });
}

const DIVIDEND_PLAN: { ticker: string; type: DividendType; every: number; perShare: number; offset: number }[] = [
  { ticker: "WEGE3", type: "JCP", every: 3, perShare: 0.11, offset: 1 },
  { ticker: "ITUB4", type: "JCP", every: 1, perShare: 0.0174, offset: 0 },
  { ticker: "ITUB4", type: "DIVIDEND", every: 6, perShare: 1.12, offset: 2 },
  { ticker: "PETR4", type: "DIVIDEND", every: 3, perShare: 0.94, offset: 2 },
  { ticker: "PETR4", type: "JCP", every: 6, perShare: 0.42, offset: 5 },
  { ticker: "VALE3", type: "DIVIDEND", every: 6, perShare: 2.09, offset: 2 },
  { ticker: "EGIE3", type: "DIVIDEND", every: 6, perShare: 1.21, offset: 3 },
  { ticker: "KLBN11", type: "DIVIDEND", every: 3, perShare: 0.42, offset: 1 },
  { ticker: "RADL3", type: "JCP", every: 6, perShare: 0.16, offset: 4 },
  { ticker: "HGLG11", type: "INCOME", every: 1, perShare: 1.1, offset: 0 },
  { ticker: "KNRI11", type: "INCOME", every: 1, perShare: 1.0, offset: 0 },
  { ticker: "AAPL34", type: "DIVIDEND", every: 3, perShare: 0.06, offset: 1 },
];

export function buildDividends(): Dividend[] {
  const out: Dividend[] = [];
  let id = 1;
  const classOf = Object.fromEntries(HOLDINGS.map((h) => [h.ticker, h.asset_class]));
  const qtyOf = Object.fromEntries(HOLDINGS.map((h) => [h.ticker, h.quantity]));
  for (let m = 0; m < 46; m++) {
    const year = 2023 + Math.floor(m / 12);
    const month = (m % 12) + 1;
    for (const plan of DIVIDEND_PLAN) {
      if ((m + plan.offset) % plan.every !== 0) continue;
      const growth = Math.min(1, 0.35 + m / 40);
      const qty = Math.max(1, Math.round(qtyOf[plan.ticker] * growth));
      const ex = `${year}-${String(month).padStart(2, "0")}-${String(8 + (hash(plan.ticker) % 15)).padStart(2, "0")}`;
      const pay = addDays(ex, plan.type === "INCOME" ? 7 : 24);
      if (ex > addDays(TODAY, 20)) continue;
      const gross = qty * plan.perShare;
      const rate = plan.type === "JCP" ? (pay >= "2026-01-01" ? 0.175 : 0.15) : 0;
      const tax = gross * rate;
      const status = pay > TODAY ? "ANNOUNCED" : pay >= "2026-08-15" ? "PAID" : "CONFIRMED";
      out.push({
        id: id++,
        ticker: plan.ticker,
        asset_class: classOf[plan.ticker],
        type: plan.type,
        status,
        ex_date: ex,
        pay_date: pay,
        quantity: String(qty),
        amount_per_share: d4(plan.perShare),
        gross: d2(gross),
        tax: d2(tax),
        net: d2(gross - tax),
        source: status === "CONFIRMED" ? "B3" : "AUTO",
      });
    }
  }
  // A dividend announced without a payment date yet.
  out.push({
    id: id++,
    ticker: "EGIE3",
    asset_class: "STOCK",
    type: "DIVIDEND",
    status: "ANNOUNCED",
    ex_date: "2026-10-14",
    pay_date: null,
    quantity: "150",
    amount_per_share: "0.6120",
    gross: "91.80",
    tax: "0.00",
    net: "91.80",
    source: "AUTO",
  });
  return out.sort((a, b) => (b.pay_date ?? "9999").localeCompare(a.pay_date ?? "9999"));
}

const BROKERS = ["XP Investimentos", "Inter DTVM", "BTG Pactual"];

export function buildTransactions(): Transaction[] {
  const rand = rng(23);
  const out: Transaction[] = [];
  let id = 1;
  const base = (t: Partial<Transaction> & Pick<Transaction, "date" | "ticker" | "type" | "quantity">): Transaction => ({
    id: id++,
    price: null,
    costs: null,
    factor: null,
    target_ticker: null,
    broker: null,
    note: null,
    source: "MANUAL",
    possible_duplicate: false,
    user_edited: false,
    gross_amount: null,
    tax_withheld: null,
    net_amount: null,
    ...t,
  });
  for (const h of HOLDINGS) {
    const lots = 2 + (hash(h.ticker) % 3);
    let remaining = h.quantity;
    for (let i = 0; i < lots; i++) {
      const qty = i === lots - 1 ? remaining : Math.max(1, Math.round((h.quantity / lots) * (0.7 + rand() * 0.5)));
      remaining -= qty;
      if (qty <= 0) continue;
      const day = 20 + Math.floor(rand() * 1300);
      const date = addDays("2023-01-02", day);
      out.push(
        base({
          date: isWeekday(date) ? date : addDays(date, 2),
          ticker: h.ticker,
          type: "BUY",
          quantity: String(qty),
          price: d2(h.avg * (0.92 + rand() * 0.16)),
          costs: rand() > 0.5 ? d2(0.03 * qty) : null,
          broker: BROKERS[Math.floor(rand() * BROKERS.length)],
          source: rand() > 0.45 ? "B3" : "MANUAL",
        }),
      );
    }
  }
  out.push(
    base({ date: "2024-03-12", ticker: "MGLU3", type: "BUY", quantity: "200", price: "2.14", broker: "Inter DTVM", source: "B3" }),
    base({ date: "2024-05-28", ticker: "MGLU3", type: "REVERSE_SPLIT", quantity: "20", factor: "10", source: "AUTO", note: "Grupamento 10:1" }),
    base({ date: "2025-02-17", ticker: "MGLU3", type: "SELL", quantity: "20", price: "9.85", broker: "Inter DTVM", source: "B3" }),
    base({ date: "2025-06-10", ticker: "PETR4", type: "SELL", quantity: "40", price: "38.90", broker: "XP Investimentos", source: "B3" }),
    base({ date: "2026-09-22", ticker: "ITUB4", type: "BONUS", quantity: "30", price: null, source: "AUTO", note: "Bonificação de 10% — custo atribuído pendente" }),
    base({ date: "2026-08-14", ticker: "PETR4", type: "BUY", quantity: "50", price: "35.42", broker: "XP Investimentos", source: "MANUAL", possible_duplicate: true }),
    base({ date: "2024-04-17", ticker: "WEGE3", type: "SPLIT", quantity: "60", factor: "2", source: "AUTO", user_edited: true, note: "Desdobramento 1:2" }),
  );
  for (const div of buildDividends().filter((d) => d.status !== "ANNOUNCED").slice(0, 60)) {
    out.push(
      base({
        date: div.pay_date ?? div.ex_date,
        ticker: div.ticker,
        type: div.type,
        quantity: div.quantity,
        price: div.amount_per_share,
        gross_amount: div.gross,
        tax_withheld: div.tax,
        net_amount: div.net,
        source: div.source,
      }),
    );
  }
  return out.sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
}

export const SEARCH_UNIVERSE: AssetSearchResult[] = [
  ...HOLDINGS.map((h) => ({ ticker: h.ticker, name: h.name, asset_class: h.asset_class })),
  { ticker: "BBDC4", name: "Bradesco", asset_class: "STOCK" },
  { ticker: "ABEV3", name: "Ambev", asset_class: "STOCK" },
  { ticker: "B3SA3", name: "B3", asset_class: "STOCK" },
  { ticker: "SUZB3", name: "Suzano", asset_class: "STOCK" },
  { ticker: "PRIO3", name: "PetroRio", asset_class: "STOCK" },
  { ticker: "SBSP3", name: "Sabesp", asset_class: "STOCK" },
  { ticker: "RENT3", name: "Localiza", asset_class: "STOCK" },
  { ticker: "LREN3", name: "Lojas Renner", asset_class: "STOCK" },
  { ticker: "TOTS3", name: "Totvs", asset_class: "STOCK" },
  { ticker: "MGLU3", name: "Magazine Luiza", asset_class: "STOCK" },
  { ticker: "XPML11", name: "XP Malls", asset_class: "FII" },
  { ticker: "MXRF11", name: "Maxi Renda", asset_class: "FII" },
  { ticker: "SMAL11", name: "iShares Small Cap", asset_class: "ETF" },
  { ticker: "MSFT34", name: "Microsoft (BDR)", asset_class: "BDR" },
];

const SECTOR_OF: Record<string, string> = {
  BBDC4: "Financeiro",
  ABEV3: "Bebidas",
  B3SA3: "Financeiro",
  SUZB3: "Papel e celulose",
  PRIO3: "Petróleo e gás",
  SBSP3: "Saneamento",
  RENT3: "Aluguel de carros",
  LREN3: "Varejo",
  TOTS3: "Tecnologia",
  MGLU3: "Varejo",
};

const FINANCIAL = new Set(["Financeiro"]);
const UTILITY = new Set(["Energia elétrica", "Saneamento"]);

function scoreOf(value: number, bad: number, good: number): number {
  const t = (value - bad) / (good - bad);
  return Math.max(0, Math.min(1, t));
}

function statusOf(ratio: number | null): Indicator["status"] {
  if (ratio === null) return "NA";
  if (ratio >= 0.7) return "GOOD";
  if (ratio >= 0.3) return "MID";
  return "BAD";
}

const PROFILES: Record<string, { q: number; p: number }> = {
  WEGE3: { q: 0.95, p: 0.15 },
  ITUB4: { q: 0.85, p: 0.75 },
  VALE3: { q: 0.8, p: 0.85 },
  PETR4: { q: 0.5, p: 0.9 },
  EGIE3: { q: 0.6, p: 0.5 },
  KLBN11: { q: 0.45, p: 0.6 },
  RADL3: { q: 0.55, p: 0.2 },
};

export function buildAnalysis(ticker: string): AssetAnalysis | null {
  const known = SEARCH_UNIVERSE.find((a) => a.ticker === ticker);
  if (!known) return null;
  const holding = HOLDINGS.find((h) => h.ticker === ticker);
  const sector = holding?.sector ?? SECTOR_OF[ticker] ?? null;
  const rand = rng(hash(ticker));
  const price = holding?.price ?? Number((10 + rand() * 60).toFixed(2));
  const base: Omit<AssetAnalysis, "decision" | "score_final" | "score_quality" | "score_price" | "eliminatory" | "indicators" | "graham_fair_price" | "graham_margin_pct" | "bazin_ceiling" | "dy_5y_pct" | "valuation" | "quality_inconclusive" | "price_inconclusive"> = {
    ticker,
    name: known.name,
    sector,
    special_sector: sector && FINANCIAL.has(sector) ? "FINANCIAL" : sector && UTILITY.has(sector) ? "UTILITY" : null,
    asset_class: known.asset_class,
    price: d2(price),
    price_date: "2026-10-07",
    day_change_pct: d2((rand() - 0.5) * 3),
    fundamentals_ref: "ITR 2T26 · DFP 2025",
    fundamentals_date: "2026-06-30",
    warnings: [],
    stale: false,
    score_price_fundamental: null,
    score_technical: null,
    technical_weight: 0,
    technical: null,
  };
  if (known.asset_class !== "STOCK") {
    return {
      ...base,
      decision: "WAIT",
      score_final: null,
      score_quality: null,
      score_price: null,
      quality_inconclusive: false,
      price_inconclusive: false,
      eliminatory: [],
      indicators: [],
      graham_fair_price: null,
      graham_margin_pct: null,
      bazin_ceiling: null,
      dy_5y_pct: null,
      valuation: null,
    };
  }
  const financial = base.special_sector === "FINANCIAL";
  const utility = base.special_sector === "UTILITY";
  const radl = ticker === "RADL3";

  type Def = { key: string; label: string; group: "QUALITY" | "PRICE"; unit: Indicator["unit"]; bad: number; good: number; range: string; value: number | null; weight: number; payout?: boolean };
  // Each demo ticker has a quality/price profile (0 = bad end of the range, 1 = optimal end).
  const profile = PROFILES[ticker] ?? { q: 0.3 + rand() * 0.5, p: 0.2 + rand() * 0.6 };
  const at = (bias: number, bad: number, good: number) => {
    const t = Math.max(-0.2, Math.min(1.2, bias + (rand() - 0.5) * 0.45));
    return bad + (good - bad) * t;
  };
  const ql = (bad: number, good: number) => at(profile.q, bad, good);
  const pr = (bad: number, good: number) => at(profile.p, bad, good);
  const qualityWeight = financial ? 100 / 3 : 12.5;
  const priceWeight = financial ? 100 / 3 : 20;
  const lpa = price / pr(25, 8);
  const vpa = price / pr(3, 1);
  const graham = Math.sqrt(22.5 * lpa * vpa);
  const proventos5y = (price * pr(2, 8)) / 100;
  const bazin = proventos5y / 0.06;
  const all: (Def & { financialOk: boolean })[] = [
    { key: "roe_5y", label: "ROE médio 5a", group: "QUALITY", unit: "pct", bad: 8, good: 20, range: "8% → 20%", value: ql(8, 20), weight: qualityWeight, financialOk: true },
    { key: "roic", label: "ROIC", group: "QUALITY", unit: "pct", bad: 6, good: 15, range: "6% → 15%", value: radl ? null : ql(6, 15), weight: qualityWeight, financialOk: false },
    { key: "net_margin_5y", label: "Margem líquida média", group: "QUALITY", unit: "pct", bad: 5, good: 15, range: "5% → 15%", value: radl ? null : ql(5, 15), weight: qualityWeight, financialOk: false },
    { key: "earnings_cagr_5y", label: "CAGR lucro 5a", group: "QUALITY", unit: "pct", bad: 0, good: 12, range: "0% → 12%", value: radl ? null : ql(0, 12), weight: qualityWeight, financialOk: true },
    { key: "net_debt_ebitda", label: "Dívida líq. / EBITDA", group: "QUALITY", unit: "x", bad: 3, good: 0.5, range: "3,0 → 0,5", value: ticker === "KLBN11" ? 4.1 : ql(3, 0.5), weight: qualityWeight, financialOk: false },
    { key: "revenue_cagr_5y", label: "CAGR receita 5a", group: "QUALITY", unit: "pct", bad: 0, good: 10, range: "0% → 10%", value: ql(0, 10), weight: qualityWeight, financialOk: false },
    { key: "current_ratio", label: "Liquidez corrente", group: "QUALITY", unit: "ratio", bad: 0.8, good: 1.5, range: "0,8 → 1,5", value: ql(0.8, 1.5), weight: qualityWeight, financialOk: false },
    { key: "payout_5y", label: "Payout médio", group: "QUALITY", unit: "pct", bad: 0, good: 25, range: "ótimo entre 25% e 80%", value: ql(10, 55), weight: qualityWeight, financialOk: true, payout: true },
    { key: "graham_margin", label: "Margem de segurança Graham", group: "PRICE", unit: "pct", bad: -20, good: 30, range: "−20% → +30%", value: ((graham - price) / price) * 100, weight: priceWeight, financialOk: false },
    { key: "pe", label: "P/L", group: "PRICE", unit: "x", bad: 25, good: 8, range: "25 → 8", value: price / lpa, weight: priceWeight, financialOk: true },
    { key: "ev_ebit", label: "EV/EBIT", group: "PRICE", unit: "x", bad: 15, good: 6, range: "15 → 6", value: pr(15, 6), weight: priceWeight, financialOk: false },
    { key: "dy_5y", label: "DY médio 5a", group: "PRICE", unit: "pct", bad: 2, good: 8, range: "2% → 8%", value: (proventos5y / price) * 100, weight: priceWeight, financialOk: true },
    { key: "pvp", label: "P/VP", group: "PRICE", unit: "x", bad: 3, good: 1, range: "3,0 → 1,0", value: price / vpa, weight: priceWeight, financialOk: true },
  ];
  const defs = financial ? all.filter((d) => d.financialOk) : all;
  const indicators: Indicator[] = defs.map((d) => {
    let ratio: number | null = null;
    if (d.value !== null) {
      if (d.payout) {
        const v = d.value;
        ratio = v < 0 || v > 100 ? 0 : v < 25 ? v / 25 : v <= 80 ? 1 : (100 - v) / 20;
      } else ratio = scoreOf(d.value, d.bad, d.good);
    }
    return {
      key: d.key,
      label: d.label,
      group: d.group,
      value: d.value === null ? null : d.value.toFixed(2),
      unit: d.unit,
      range_label: d.range,
      points: ratio === null ? null : (ratio * d.weight).toFixed(4),
      max_points: d.weight.toFixed(4),
      status: statusOf(ratio),
      note: d.value === null ? "Sem dados na CVM para o período" : null,
    };
  });
  const score = (group: "QUALITY" | "PRICE") => {
    const items = indicators.filter((i) => i.group === group);
    const evaluated = items.filter((i) => i.points !== null);
    const got = evaluated.reduce((a, i) => a + Number(i.points), 0);
    const possible = evaluated.reduce((a, i) => a + Number(i.max_points), 0);
    const totalWeight = items.reduce((a, i) => a + Number(i.max_points), 0);
    return { score: possible ? Math.round((got / possible) * 100) : null, inconclusive: (totalWeight - possible) / totalWeight > 0.3 };
  };
  const q = score("QUALITY");
  const p = score("PRICE");
  const nde = indicators.find((i) => i.key === "net_debt_ebitda");
  const ndeValue = nde?.value ? Number(nde.value) : null;
  const eliminatory: EliminatoryCheck[] = [
    { id: "E1", label: "Lucro líquido positivo", rule: "≥ 4 de 5 anos", value_label: ticker === "KLBN11" ? "4 de 5" : "5 de 5", passed: true },
    { id: "E2", label: "Patrimônio líquido", rule: "> 0", value_label: "R$ 38,2 bi", passed: true },
    ...(financial
      ? []
      : [
          {
            id: "E3",
            label: "Dívida líquida / EBITDA",
            rule: utility ? "≤ 4,5 (utilities)" : "≤ 3,5",
            value_label: ticker === "KLBN11" ? "4,1x" : ndeValue === null ? null : `${ndeValue.toFixed(1).replace(".", ",")}x`,
            passed: ticker === "KLBN11" ? false : ndeValue === null ? null : ndeValue <= (utility ? 4.5 : 3.5),
          },
        ]),
    { id: "E4", label: "Liquidez média diária", rule: "≥ R$ 2 milhões", value_label: "R$ 214,6 mi", passed: true },
  ];
  const failed = eliminatory.some((e) => e.passed === false);
  const sq = q.score;
  // Chart analysis (F8): distance from the SMA200 → 50 − 5 × distance, blended with weight 0,25
  const distance = (profile.p - 0.5) * -24 + (rand() - 0.5) * 6;
  const tech = Math.round(Math.min(100, Math.max(0, 50 - 5 * distance)) * 10) / 10;
  const sp = p.score === null ? null : Math.round((0.75 * p.score + 0.25 * tech) * 10) / 10;
  let decision: Decision;
  if (failed) decision = "AVOID";
  else if (q.inconclusive || p.inconclusive) decision = "WAIT";
  else if ((sq ?? 0) >= 70) decision = (sp ?? 0) >= 60 ? "BUY" : "WAIT";
  else if ((sq ?? 0) >= 50) decision = "WAIT";
  else decision = "AVOID";
  return {
    ...base,
    decision,
    score_quality: sq,
    score_price: sp,
    score_price_fundamental: p.score,
    score_technical: tech,
    technical_weight: 0.25,
    technical: {
      score: tech,
      sma: d2(price / (1 + distance / 100)),
      distance_pct: d2(distance),
      price: d2(price),
      sessions: 200,
      sma_days: 200,
      cheap_pct: "-10",
      expensive_pct: "10",
      note: null,
    },
    score_final: sq !== null && sp !== null ? Math.round(0.6 * sq + 0.4 * sp) : null,
    quality_inconclusive: q.inconclusive,
    price_inconclusive: p.inconclusive,
    eliminatory,
    indicators,
    graham_fair_price: d2(graham),
    graham_margin_pct: d2(((graham - price) / price) * 100),
    bazin_ceiling: d2(bazin),
    dy_5y_pct: d2((proventos5y / price) * 100),
    valuation: {
      eps: lpa.toFixed(4),
      bvps: vpa.toFixed(4),
      net_income_ttm: d2(lpa * 1e9),
      equity: d2(vpa * 1e9),
      shares: "1000000000",
      graham_note: null,
      dps_5y: proventos5y.toFixed(4),
      dps_note: null,
      dps_by_year: [0.8, 0.9, 1, 1.1, 1.2].map((f, i) => ({ year: 2021 + i, dps: (proventos5y * f).toFixed(4) })),
    },
  };
}


function describe(i: Indicator): string {
  const v = i.value === null ? "—" : i.unit === "pct" ? formatPct(i.value, { decimals: 1 }) : formatMultiple(i.value);
  return `${i.label}: ${v}`;
}

/** The position's rules snapshot, derived from the same analysis shown on the Análise screen. */
function rulesFromAnalysis(ticker: string): RulesSnapshot | null {
  const a = buildAnalysis(ticker);
  if (!a || a.asset_class !== "STOCK" || a.score_final === null) return null;
  const inconclusive = a.quality_inconclusive || a.price_inconclusive;
  const failed = a.eliminatory.find((e) => e.passed === false);
  const ratio = (i: Indicator) => (i.points === null ? null : Number(i.points) / Number(i.max_points));
  const scored = a.indicators.filter((i) => ratio(i) !== null).sort((x, y) => ratio(x)! - ratio(y)!);
  let main_reason: string | null;
  if (failed) main_reason = `Eliminatório ${failed.id}: ${failed.label} ${failed.value_label ?? ""}`.trim();
  else if (inconclusive) main_reason = "Nota inconclusiva: mais de 30% do peso sem dados";
  else if (a.decision === "BUY") main_reason = scored.length ? describe(scored[scored.length - 1]) : null;
  else main_reason = scored.length ? describe(scored[0]) : null;
  return {
    decision: a.decision,
    score_final: a.score_final,
    score_quality: a.score_quality ?? 0,
    score_price: a.score_price ?? 0,
    inconclusive,
    main_reason,
  };
}

export function buildPriceBars(ticker: string): PriceBar[] {
  const holding = HOLDINGS.find((h) => h.ticker === ticker);
  const rand = rng(hash(ticker) ^ 99);
  const target = holding?.price ?? 30;
  const bars: { time: string; o: number; h: number; l: number; c: number; v: number }[] = [];
  let date = "2024-10-07";
  let close = target * (0.7 + rand() * 0.5);
  while (date <= "2026-10-07") {
    if (isWeekday(date)) {
      const open = close * (1 + (rand() - 0.5) * 0.012);
      close = open * (1 + (rand() - 0.495) * 0.028);
      const high = Math.max(open, close) * (1 + rand() * 0.01);
      const low = Math.min(open, close) * (1 - rand() * 0.01);
      bars.push({ time: date, o: open, h: high, l: low, c: close, v: 2e6 + rand() * 8e6 });
    }
    date = addDays(date, 1);
  }
  const scale = target / bars[bars.length - 1].c;
  return bars.map((b, i) => {
    const s = Math.pow(scale, i / (bars.length - 1));
    return { time: b.time, open: d2(b.o * s), high: d2(b.h * s), low: d2(b.l * s), close: d2(b.c * s), volume: b.v.toFixed(0) };
  });
}

export function buildImportPreview(fileName: string): ImportPreview {
  const movement = /moviment/i.test(fileName);
  const rows: ImportPreviewRow[] = movement
    ? [
        { line: 2, date: "2026-09-30", ticker: "HGLG11", kind: "Rendimento", mapped_type: "INCOME", quantity: "25", price: "1.10", value: "27.50", broker: "XP Investimentos", status: "NEW", reason: null },
        { line: 3, date: "2026-09-12", ticker: "ITUB4", kind: "Juros Sobre Capital Próprio", mapped_type: "JCP", quantity: "300", price: "0.0174", value: "4.31", broker: "XP Investimentos", status: "DUPLICATE", reason: "Já lançado automaticamente (confirma o provento)" },
        { line: 4, date: "2026-09-10", ticker: "PETR4", kind: "Transferência - Liquidação", mapped_type: null, quantity: "50", price: "35.42", value: "1771.00", broker: "XP Investimentos", status: "IGNORED", reason: "Liquidação de compra — já vem no extrato de Negociação" },
        { line: 5, date: "2026-08-22", ticker: "ITUB4", kind: "Bonificação em Ativos", mapped_type: "BONUS", quantity: "30", price: null, value: null, broker: "XP Investimentos", status: "NEW", reason: "Custo atribuído não informado" },
        { line: 6, date: "2026-08-13", ticker: "WEGE3", kind: "Transferência", mapped_type: null, quantity: "120", price: null, value: null, broker: "BTG Pactual", status: "IGNORED", reason: "Transferência de custódia entre corretoras" },
        { line: 7, date: "2025-09-11", ticker: "WDOV25", kind: "Compra", mapped_type: null, quantity: "0", price: "5424", value: null, broker: "Corretora X", status: "IGNORED", reason: "Mercado futuro — fora do escopo da carteira" },
        { line: 8, date: "2025-07-11", ticker: "CDB", kind: "Resgate antecipado", mapped_type: null, quantity: "1000", price: "1.02", value: "1020.00", broker: "Banco X", status: "IGNORED", reason: "Renda fixa — fora do escopo" },
        { line: 9, date: "2025-02-27", ticker: "VALE3", kind: "Dividendo", mapped_type: "DIVIDEND", quantity: "90", price: "2.0900", value: "188.10", broker: "Inter DTVM", status: "NEW", reason: null },
      ]
    : [
        { line: 2, date: "2026-09-18", ticker: "WEGE3", kind: "Compra · Mercado à Vista", mapped_type: "BUY", quantity: "20", price: "50.12", value: "1002.40", broker: "XP Investimentos", status: "NEW", reason: null },
        { line: 3, date: "2026-08-14", ticker: "PETR4", kind: "Compra · Mercado à Vista", mapped_type: "BUY", quantity: "50", price: "35.42", value: "1771.00", broker: "XP Investimentos", status: "DUPLICATE", reason: "Igual a um lançamento já importado" },
        { line: 4, date: "2026-07-03", ticker: "EGIE3F", kind: "Compra · Mercado Fracionário", mapped_type: "BUY", quantity: "15", price: "42.80", value: "642.00", broker: "Inter DTVM", status: "NEW", reason: "Ticker fracionário normalizado para EGIE3" },
        { line: 5, date: "2025-12-18", ticker: "WDOF26", kind: "Venda · Futuro", mapped_type: null, quantity: "1", price: "5512", value: "55120.00", broker: "Corretora X", status: "IGNORED", reason: "Mercado futuro — fora do escopo da carteira" },
        { line: 6, date: "2025-12-18", ticker: "WDOF26", kind: "Compra · Futuro", mapped_type: null, quantity: "1", price: "5498", value: "54980.00", broker: "Corretora X", status: "IGNORED", reason: "Mercado futuro — fora do escopo da carteira" },
        { line: 7, date: "2025-11-04", ticker: "VALE3", kind: "Venda · Mercado à Vista", mapped_type: "SELL", quantity: "10", price: "61.90", value: "619.00", broker: "Inter DTVM", status: "NEW", reason: null },
        { line: 8, date: "2025-06-10", ticker: "PETR4", kind: "Venda · Mercado à Vista", mapped_type: "SELL", quantity: "40", price: "38.90", value: "1556.00", broker: "XP Investimentos", status: "DUPLICATE", reason: "Igual a um lançamento já importado" },
        { line: 9, date: "2025-03-14", ticker: "XYZW3", kind: "Compra · Mercado à Vista", mapped_type: "BUY", quantity: "abc", price: null, value: null, broker: "Inter DTVM", status: "ERROR", reason: "Quantidade inválida na linha" },
      ];
  const counts = { NEW: 0, DUPLICATE: 0, IGNORED: 0, ERROR: 0 };
  for (const r of rows) counts[r.status]++;
  return { id: `prev-${hash(fileName)}`, file_name: fileName, file_kind: movement ? "MOVEMENT" : "NEGOTIATION", rows, counts };
}
