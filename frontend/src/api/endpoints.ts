/**
 * Every backend call goes through this file. Backend payloads (app/schemas/*.py) are translated here
 * into the UI contracts of ./types, so screens never depend on the wire format.
 *
 * MOCK SWITCH: VITE_USE_MOCKS=true (frontend/.env.local) serves demo data instead of the FastAPI backend.
 * Backend percentages are fractions ("0.1234"); the UI uses percentage points ("12.34").
 */
import { ApiError, http } from "./client";
import type {
  AssetAnalysis,
  AssetSearchResult,
  Dividend,
  EquityPoint,
  ImportPreview,
  ImportResult,
  ImportRowStatus,
  PendingItem,
  PortfolioSummary,
  Position,
  PriceBar,
  ReportDispatch,
  ReportPreview,
  WatchItem,
  Watchlist,
  WatchlistPreview,
  ReturnPoint,
  SourceWarning,
  Transaction,
  TransactionFilters,
  TransactionInput,
} from "./types";
import type * as W from "./wire";

type MockServer = typeof import("@/mocks/server").mockServer;

/** Demo data is loaded on demand, so it never ships in the main bundle. */
const mock = <T>(call: (server: MockServer) => Promise<T>): Promise<T> =>
  import("@/mocks/server").then((m) => call(m.mockServer));

export const USE_MOCKS = (import.meta.env.VITE_USE_MOCKS ?? "false") === "true";

/** Fraction string → percentage points string, keeping decimal-string semantics. */
export function toPct(fraction: string | null | undefined): string | null {
  if (fraction === null || fraction === undefined) return null;
  return String(Math.round(Number(fraction) * 1e6) / 1e4);
}

const today = () => new Date().toISOString().slice(0, 10);

function toWatchItem(w: W.WatchItem): WatchItem {
  const { distance, ...rest } = w;
  return { ...rest, distance_pct: toPct(distance) };
}

const MOCK_WATCHLIST: Watchlist = {
  items: [],
  channel: null,
  report_time: "19:00",
  sma_days: 200,
  cheap_pct: "-10",
  expensive_pct: "10",
  last_scheduled: null,
};

function toPosition(p: W.Position): Position {
  return {
    ticker: p.ticker,
    name: p.name ?? p.ticker,
    asset_class: p.asset_class,
    sector: p.sector,
    quantity: p.quantity,
    avg_price: p.avg_price,
    last_price: p.current_price,
    price_date: p.price_date,
    day_change_pct: toPct(p.day_change_pct),
    market_value: p.market_value ?? p.total_cost,
    cost_basis: p.total_cost,
    weight_pct: toPct(p.weight_pct) ?? "0",
    pnl: p.open_result ?? "0",
    pnl_pct: toPct(p.open_result_pct) ?? "0",
    dividends_received: p.provents_net,
    yield_on_cost_pct: toPct(p.yield_on_cost_pct),
    pending_cost: p.pending_bonus_cost,
    rules: p.rules
      ? {
          decision: p.rules.decision,
          score_final: p.rules.score_final ?? 0,
          score_quality: p.rules.score_quality ?? 0,
          score_price: p.rules.score_price ?? 0,
          inconclusive: p.rules.inconclusive,
          main_reason: p.rules.main_reason,
        }
      : null,
  };
}

const SOURCE_LABEL: Record<string, string> = { prices: "Cotações", ibov: "Ibovespa", cdi: "CDI" };

function toWarnings(statuses: W.DataSourceStatus[]): SourceWarning[] {
  return statuses
    .filter((s) => !s.ok)
    .map((s) => ({
      source: SOURCE_LABEL[s.source] ?? s.source,
      message: s.message ?? "falha na última atualização",
      last_success_at: s.last_success_at,
    }));
}

async function getSummary(): Promise<PortfolioSummary> {
  const [s, statuses] = await Promise.all([
    http.get<W.Summary>("/portfolio/summary"),
    http.get<W.DataSourceStatus[]>("/data-sources").catch(() => []),
  ]);
  const dayChange = Number(s.day_change ?? 0);
  const previous = Number(s.market_value) - dayChange;
  return {
    as_of: today(),
    prices_as_of: s.prices_as_of,
    equity: s.market_value,
    invested: s.invested,
    unrealized_pnl: s.open_result,
    realized_pnl: s.realized_result,
    total_return_pct: toPct(s.return_total) ?? "0",
    return_12m_pct: toPct(s.return_12m) ?? "0",
    day_change: s.day_change ?? "0",
    day_change_pct: previous ? String(Math.round((dayChange / previous) * 1e6) / 1e4) : "0",
    dividends_12m: s.provents_net_12m,
    dividends_total: s.provents_net_total,
    dividends_receivable: s.provents_receivable,
    warnings: toWarnings(statuses),
  };
}

function toTransaction(t: W.Transaction): Transaction {
  return {
    id: t.id,
    date: t.date,
    ticker: t.ticker,
    type: t.type,
    quantity: t.quantity,
    price: t.price,
    costs: t.costs,
    factor: t.factor,
    target_ticker: t.target_ticker,
    broker: t.broker,
    note: t.notes,
    source: t.source,
    possible_duplicate: false,
    user_edited: t.user_edited,
    gross_amount: t.gross_amount,
    tax_withheld: t.tax_withheld,
    net_amount: t.net_amount,
  };
}

function toWireInput(input: TransactionInput): W.TransactionIn {
  const { note, quantity, ...rest } = input;
  return { ...rest, quantity: quantity && Number(quantity) !== 0 ? quantity : null, notes: note ?? null };
}

/** Backend issues {code, message, row, field} → UI issues {field: "row.field" | "field", message}. */
function guessField(issue: W.Issue): string {
  if (issue.field) return issue.field;
  if (issue.code === "INSUFFICIENT_POSITION" || issue.code === "NO_POSITION") return "quantity";
  if (/futuro/i.test(issue.message)) return "date";
  if (/fator/i.test(issue.message)) return "factor";
  return "quantity";
}

function translateErrors<T>(promise: Promise<T>): Promise<T> {
  return promise.catch((err: unknown) => {
    if (err instanceof ApiError && Array.isArray(err.detail)) {
      const issues = (err.detail as W.Issue[]).map((i) => ({
        field: i.row !== null && i.row !== undefined ? `${i.row}.${guessField(i)}` : guessField(i),
        message: i.message,
        severity: "error" as const,
      }));
      const message = issues.map((i) => i.message).join(" · ") || err.message;
      throw new ApiError(err.status, message, issues);
    }
    throw err;
  });
}

function toDividend(p: W.Provent): Dividend {
  return {
    id: p.id,
    ticker: p.ticker,
    asset_class: p.asset_class,
    type: p.type,
    status: p.status,
    ex_date: p.record_date,
    pay_date: p.payment_date,
    quantity: p.quantity,
    amount_per_share: p.value_per_share ?? "0",
    gross: p.gross_amount,
    tax: p.tax_withheld,
    net: p.net_amount,
    source: p.source,
  };
}

/** Announced cash events whose data-com is still ahead, as estimated agenda entries. */
async function getAgendaEstimates(): Promise<Dividend[]> {
  const items = await http.get<W.AgendaItem[]>("/provents/agenda");
  return items
    .filter((i) => !i.in_ledger && i.estimated_net !== null)
    .map((i, index) => ({
      id: -(index + 1),
      ticker: i.ticker,
      asset_class: "STOCK" as const,
      type: i.kind as Dividend["type"],
      status: "ANNOUNCED" as const,
      ex_date: i.record_date,
      pay_date: i.payment_date,
      quantity: i.quantity,
      amount_per_share: i.value,
      gross: i.estimated_net!,
      tax: "0",
      net: i.estimated_net!,
      source: "AUTO" as const,
    }));
}

// The backend import is stateless: the preview keeps the File so commit can upload it again.
const pendingImports = new Map<string, File>();

const IMPORT_STATUS: Record<W.ImportRow["status"], ImportRowStatus> = {
  NEW: "NEW",
  DUPLICATE: "DUPLICATE",
  POSSIBLE_DUPLICATE: "DUPLICATE",
  IGNORED: "IGNORED",
  ERROR: "ERROR",
};

function filesForm(file: File): FormData {
  const form = new FormData();
  form.append("files", file);
  return form;
}

async function previewImport(file: File): Promise<ImportPreview> {
  const report = await http.post<W.ImportReport>("/import/b3/preview", filesForm(file));
  const id = crypto.randomUUID();
  pendingImports.set(id, file);
  const rows = report.rows.map((r) => ({
    line: r.line,
    date: r.date,
    ticker: r.ticker,
    kind: r.raw["Movimentação"] || [r.raw["Tipo de Movimentação"], r.raw["Mercado"]].filter(Boolean).join(" · "),
    mapped_type: r.type,
    quantity: r.quantity,
    price: r.price,
    value: r.gross_amount,
    broker: r.broker,
    status: IMPORT_STATUS[r.status],
    reason: r.reason,
  }));
  const counts: Record<ImportRowStatus, number> = { NEW: 0, DUPLICATE: 0, IGNORED: 0, ERROR: 0 };
  for (const row of rows) counts[row.status] += 1;
  return {
    id,
    file_name: file.name,
    file_kind: Object.values(report.files)[0] === "b3_negociacao" ? "NEGOTIATION" : "MOVEMENT",
    rows,
    counts,
  };
}

async function commitImport(previewId: string): Promise<ImportResult> {
  const file = pendingImports.get(previewId);
  if (!file) throw new ApiError(0, "A prévia expirou. Envie o arquivo novamente.");
  const report = await http.post<W.ImportReport>("/import/b3/commit", filesForm(file));
  pendingImports.delete(previewId);
  const c = report.counts;
  return {
    inserted: report.inserted,
    duplicates: (c.DUPLICATE ?? 0) + (c.POSSIBLE_DUPLICATE ?? 0),
    ignored: c.IGNORED ?? 0,
    errors: c.ERROR ?? 0,
  };
}

function fundamentalsRef(a: W.Analysis): string | null {
  const fmt = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;
  const parts = [a.last_dfp && `DFP ${fmt(a.last_dfp)}`, a.last_itr && `ITR ${fmt(a.last_itr)}`].filter(Boolean);
  return parts.length ? parts.join(" + ") : null;
}

/** Five years of daily bars for the price chart (the backend keeps ~6 years for the indicator history). */
const PRICE_HISTORY_DAYS = 5 * 365 + 2;

function toAnalysis(a: W.Analysis): AssetAnalysis {
  return {
    ticker: a.ticker,
    name: a.name,
    sector: a.sector,
    special_sector: a.special_sector,
    asset_class: "STOCK",
    price: a.price,
    price_date: a.price_date,
    day_change_pct: toPct(a.day_change),
    fundamentals_ref: fundamentalsRef(a),
    fundamentals_date: a.last_itr ?? a.last_dfp,
    decision: a.decision,
    score_final: a.score_final,
    score_quality: a.score_quality,
    score_price: a.score_price,
    quality_inconclusive: a.quality_inconclusive,
    price_inconclusive: a.price_inconclusive,
    stale: a.stale,
    score_price_fundamental: a.score_price_fundamental,
    score_technical: a.score_technical,
    technical_weight: a.technical_weight,
    technical: a.technical && {
      score: a.technical.score,
      sma: a.technical.sma,
      distance_pct: toPct(a.technical.distance),
      price: a.technical.price,
      sessions: a.technical.sessions,
      sma_days: a.technical.sma_days,
      cheap_pct: toPct(a.technical.cheap) ?? "0",
      expensive_pct: toPct(a.technical.expensive) ?? "0",
      note: a.technical.note,
    },
    eliminatory: a.eliminatory,
    indicators: a.indicators.map((i) => ({
      key: i.key,
      label: i.label,
      group: i.group,
      value: i.unit === "pct" ? toPct(i.value) : i.value,
      unit: i.unit,
      range_label: i.range_label,
      points: i.points === null ? null : String(i.points),
      max_points: String(i.weight),
      status: i.status,
      note: i.note,
    })),
    fundamentals: a.fundamentals.map((f) => ({ ...f, value: f.unit === "pct" ? toPct(f.value) : f.value })),
    history: a.history.map(({ net_margin, ebit_margin, roe, roic, payout, dy, ...h }) => ({
      ...h,
      net_margin_pct: toPct(net_margin),
      ebit_margin_pct: toPct(ebit_margin),
      roe_pct: toPct(roe),
      roic_pct: toPct(roic),
      payout_pct: toPct(payout),
      dy_pct: toPct(dy),
    })),
    graham_fair_price: a.graham_price,
    graham_margin_pct: toPct(a.graham_margin),
    bazin_ceiling: a.bazin_price,
    dy_5y_pct: toPct(a.dy_5y),
    valuation: a.valuation,
    warnings: a.warnings
      .filter((w) => !w.startsWith("análise parcial") && !w.startsWith("setor cíclico"))
      .map((w) => ({ source: "Análise", message: w, last_success_at: null })),
  };
}

async function getAnalysis(ticker: string): Promise<AssetAnalysis> {
  try {
    return toAnalysis(await http.get<W.Analysis>(`/analysis/${encodeURIComponent(ticker)}`));
  } catch (err) {
    // The page shows a friendly empty state for unknown tickers
    if (err instanceof ApiError && err.status === 404) throw new ApiError(404, err.message);
    throw err;
  }
}

export const api = {
  // Portfolio
  getSummary: (): Promise<PortfolioSummary> => (USE_MOCKS ? mock((s) => s.summary()) : getSummary()),
  getPositions: (): Promise<Position[]> =>
    USE_MOCKS
      ? mock((s) => s.positions())
      : http.get<W.Position[]>("/portfolio/positions").then((ps) => ps.map(toPosition)),
  getPending: (): Promise<PendingItem[]> =>
    USE_MOCKS ? mock((s) => s.pending()) : http.get<PendingItem[]>("/portfolio/pending"),
  getEquitySeries: (): Promise<EquityPoint[]> =>
    USE_MOCKS
      ? mock((s) => s.equitySeries())
      : http
          .get<W.HistoryPoint[]>("/portfolio/history", { range: "all" })
          .then((ps) => ps.map((p) => ({ date: p.date, equity: p.market_value, invested: p.invested }))),
  getReturnSeries: (): Promise<ReturnPoint[]> =>
    USE_MOCKS
      ? mock((s) => s.returnSeries())
      : http.get<W.HistoryPoint[]>("/portfolio/history", { range: "all" }).then((ps) =>
          ps.map((p) => ({
            date: p.date,
            portfolio_pct: toPct(p.portfolio_return) ?? "0",
            ibov_pct: toPct(p.ibov_return),
            cdi_pct: toPct(p.cdi_return),
          })),
        ),

  // Transactions
  getTransactions: (filters: TransactionFilters = {}): Promise<Transaction[]> =>
    USE_MOCKS
      ? mock((s) => s.transactions(filters))
      : http
          .get<W.Transaction[]>("/transactions", {
            ticker: filters.ticker,
            type: filters.type === "ALL" ? undefined : filters.type,
            source: filters.source === "ALL" ? undefined : filters.source,
            date_from: filters.from,
            date_to: filters.to,
          })
          .then((ts) => ts.map(toTransaction)),
  createTransaction: (input: TransactionInput): Promise<Transaction> =>
    USE_MOCKS
      ? mock((s) => s.createTransaction(input))
      : translateErrors(http.post<W.Transaction>("/transactions", toWireInput(input))).then(toTransaction),
  createTransactionsBatch: (inputs: TransactionInput[]): Promise<Transaction[]> =>
    USE_MOCKS
      ? mock((s) => s.createTransactionsBatch(inputs))
      : translateErrors(
          http.post<W.Transaction[]>("/transactions/batch", { items: inputs.map(toWireInput) }),
        ).then((ts) => ts.map(toTransaction)),
  updateTransaction: (id: number, input: TransactionInput): Promise<Transaction> =>
    USE_MOCKS
      ? mock((s) => s.updateTransaction(id, input))
      : translateErrors(http.put<W.Transaction>(`/transactions/${id}`, toWireInput(input))).then(toTransaction),
  deleteTransaction: (id: number): Promise<void> =>
    USE_MOCKS ? mock((s) => s.deleteTransaction(id)) : translateErrors(http.delete(`/transactions/${id}`)),

  // Dividends
  getDividends: (): Promise<Dividend[]> =>
    USE_MOCKS ? mock((s) => s.dividends()) : http.get<W.Provent[]>("/provents").then((ps) => ps.map(toDividend)),
  getAgendaEstimates: (): Promise<Dividend[]> => (USE_MOCKS ? Promise.resolve([]) : getAgendaEstimates()),

  // Assets & analysis
  searchAssets: (q: string): Promise<AssetSearchResult[]> =>
    USE_MOCKS
      ? mock((s) => s.searchAssets(q))
      : http
          .get<W.Asset[]>("/assets/search", { q })
          .then((as) => as.map((a) => ({ ticker: a.ticker, name: a.name ?? a.ticker, asset_class: a.asset_class }))),
  getAnalysis: (ticker: string): Promise<AssetAnalysis> =>
    USE_MOCKS ? mock((s) => s.analysis(ticker)) : getAnalysis(ticker),
  getPriceBars: (ticker: string): Promise<PriceBar[]> =>
    USE_MOCKS
      ? mock((s) => s.priceBars(ticker))
      : http.get<W.PriceBar[]>(`/prices/${encodeURIComponent(ticker)}`, { days: PRICE_HISTORY_DAYS }).then((bars) =>
          bars.map((b) => ({
            time: b.date,
            open: b.open ?? b.close,
            high: b.high ?? b.close,
            low: b.low ?? b.close,
            close: b.close,
            volume: b.volume ?? "0",
          })),
        ),
  refreshPrices: (): Promise<{ updated: number; failed: number }> =>
    USE_MOCKS
      ? mock((s) => s.refreshPrices())
      : Promise.all([
          http.post<W.Refresh>("/market-data/refresh"),
          http.post<W.EventsSync>("/corporate-events/sync"),
        ])
          // Decisions use the fresh quotes, so the portfolio is re-analyzed afterwards
          .then(([r, e]) =>
            http
              .post<W.PortfolioRun>("/analysis/portfolio")
              .then((run) => ({ updated: r.prices_inserted, failed: r.errors.length + e.errors.length + run.errors.length })),
          ),

  // Daily report (Discord). Mocks: a static preview; sending is not available.
  getReportPreview: (): Promise<ReportPreview> =>
    USE_MOCKS
      ? Promise.resolve({
          date: "2026-10-08",
          content: "## 📊 Carteira B3 · qui, 08/10/2026\n-# Prévia indisponível nos dados de demonstração.",
          messages: [],
          configured: false,
          report_time: "19:00",
          last_scheduled: null,
        })
      : http.get<ReportPreview>("/report/preview"),
  getReportDispatches: (): Promise<ReportDispatch[]> =>
    USE_MOCKS ? Promise.resolve([]) : http.get<ReportDispatch[]>("/report/dispatches"),
  sendReport: (): Promise<ReportDispatch> => http.post<ReportDispatch>("/report/send"),

  // Watchlist (Discord alert on the price vs. the SMA200). Mocks: an empty list, read-only.
  getWatchlist: (): Promise<Watchlist> =>
    USE_MOCKS
      ? Promise.resolve(MOCK_WATCHLIST)
      : http.get<W.Watchlist>("/watchlist").then((w) => ({
          items: w.items.map(toWatchItem),
          channel: w.channel,
          report_time: w.report_time,
          sma_days: w.sma_days,
          cheap_pct: toPct(w.cheap) ?? "-10",
          expensive_pct: toPct(w.expensive) ?? "10",
          last_scheduled: w.last_scheduled,
        })),
  addWatch: (ticker: string, note?: string): Promise<WatchItem> =>
    http.post<W.WatchItem>("/watchlist", { ticker, note: note || null }).then(toWatchItem),
  editWatch: (ticker: string, note: string): Promise<WatchItem> =>
    http.patch<W.WatchItem>(`/watchlist/${encodeURIComponent(ticker)}`, { note: note || null }).then(toWatchItem),
  removeWatch: (ticker: string): Promise<void> => http.delete<void>(`/watchlist/${encodeURIComponent(ticker)}`),
  getWatchlistPreview: (): Promise<WatchlistPreview> =>
    USE_MOCKS
      ? Promise.resolve({ date: today(), content: "## 📈 Lista de observação\n-# Prévia indisponível nos dados de demonstração.", messages: [], channel: null })
      : http.get<WatchlistPreview>("/watchlist/preview"),
  getWatchlistDispatches: (): Promise<ReportDispatch[]> =>
    USE_MOCKS ? Promise.resolve([]) : http.get<ReportDispatch[]>("/watchlist/dispatches"),
  sendWatchlist: (): Promise<ReportDispatch> => http.post<ReportDispatch>("/watchlist/send"),

  // Import
  previewImport: (file: File): Promise<ImportPreview> =>
    USE_MOCKS ? mock((s) => s.importPreview(file)) : previewImport(file),
  commitImport: (previewId: string): Promise<ImportResult> =>
    USE_MOCKS ? mock((s) => s.importCommit(previewId)) : commitImport(previewId),
};
