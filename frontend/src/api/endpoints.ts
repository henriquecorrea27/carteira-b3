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
    rules: null, // rules engine arrives in F6
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

async function getPending(): Promise<PendingItem[]> {
  const bonuses = await http.get<W.Transaction[]>("/transactions", { type: "BONUS" });
  return bonuses
    .filter((t) => t.price === null)
    .map((t) => ({
      id: `bonus-${t.id}`,
      kind: "BONUS_NO_COST" as const,
      ticker: t.ticker,
      date: t.date,
      message: `Bonificação de ${t.quantity.replace(".", ",")} ações sem custo atribuído — informe o valor do aviso aos acionistas.`,
      transaction_id: t.id,
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

const notYet = (what: string) => () =>
  Promise.reject(new ApiError(501, `${what} ainda não está disponível nesta versão (chega na fase F6).`));

export const api = {
  // Portfolio
  getSummary: (): Promise<PortfolioSummary> => (USE_MOCKS ? mock((s) => s.summary()) : getSummary()),
  getPositions: (): Promise<Position[]> =>
    USE_MOCKS
      ? mock((s) => s.positions())
      : http.get<W.Position[]>("/portfolio/positions").then((ps) => ps.map(toPosition)),
  getPending: (): Promise<PendingItem[]> => (USE_MOCKS ? mock((s) => s.pending()) : getPending()),
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

  // Assets & analysis
  searchAssets: (q: string): Promise<AssetSearchResult[]> =>
    USE_MOCKS
      ? mock((s) => s.searchAssets(q))
      : http
          .get<W.Asset[]>("/assets/search", { q })
          .then((as) => as.map((a) => ({ ticker: a.ticker, name: a.name ?? a.ticker, asset_class: a.asset_class }))),
  getAnalysis: (ticker: string): Promise<AssetAnalysis> =>
    USE_MOCKS ? mock((s) => s.analysis(ticker)) : notYet("A análise de ativos")(),
  getPriceBars: (ticker: string): Promise<PriceBar[]> =>
    USE_MOCKS ? mock((s) => s.priceBars(ticker)) : notYet("O gráfico de preços")(),
  refreshPrices: (): Promise<{ updated: number; failed: number }> =>
    USE_MOCKS
      ? mock((s) => s.refreshPrices())
      : http
          .post<W.Refresh>("/market-data/refresh")
          .then((r) => ({ updated: r.prices_inserted, failed: r.errors.length })),

  // Import
  previewImport: (file: File): Promise<ImportPreview> =>
    USE_MOCKS ? mock((s) => s.importPreview(file)) : previewImport(file),
  commitImport: (previewId: string): Promise<ImportResult> =>
    USE_MOCKS ? mock((s) => s.importCommit(previewId)) : commitImport(previewId),
};
