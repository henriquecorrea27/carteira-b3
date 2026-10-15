/**
 * API contracts.
 * Conventions:
 *  - `Decimal` fields are decimal strings ("1234.56"); never do math on them outside lib/format.
 *  - Fields ending in `_pct` are percentage points ("14.7" means 14,7%).
 *  - Dates are ISO "YYYY-MM-DD"; timestamps are ISO 8601 with offset.
 */

export type Decimal = string;
export type ISODate = string;
export type ISODateTime = string;

export type AssetClass = "STOCK" | "FII" | "ETF" | "BDR";
export type Decision = "BUY" | "WAIT" | "AVOID";
export type Source = "MANUAL" | "B3" | "AUTO";

export type TransactionType =
  | "BUY"
  | "SELL"
  | "SPLIT"
  | "REVERSE_SPLIT"
  | "BONUS"
  | "FRACTION_AUCTION"
  | "TICKER_CHANGE"
  | "DIVIDEND"
  | "JCP"
  | "INCOME";

export type DividendType = "DIVIDEND" | "JCP" | "INCOME";
export type DividendStatus = "ANNOUNCED" | "PAID" | "CONFIRMED";

/** An external data source that failed; the UI shows it and keeps the cached data. */
export interface SourceWarning {
  source: string;
  message: string;
  last_success_at: ISODateTime | null;
}

export interface RulesSnapshot {
  decision: Decision;
  score_final: number;
  score_quality: number;
  score_price: number;
  inconclusive: boolean;
  /** Main reason, e.g. "P/L 6,2 abaixo da faixa ótima". */
  main_reason: string | null;
}

export interface Position {
  ticker: string;
  name: string;
  asset_class: AssetClass;
  sector: string | null;
  quantity: Decimal;
  avg_price: Decimal;
  last_price: Decimal | null;
  price_date: ISODate | null;
  day_change_pct: Decimal | null;
  market_value: Decimal;
  cost_basis: Decimal;
  weight_pct: Decimal;
  pnl: Decimal;
  pnl_pct: Decimal;
  dividends_received: Decimal;
  yield_on_cost_pct: Decimal | null;
  /** True while a bonificação has no cost assigned: the average price is provisional. */
  pending_cost: boolean;
  rules: RulesSnapshot | null;
}

export interface PortfolioSummary {
  as_of: ISODate;
  prices_as_of: ISODateTime | null;
  equity: Decimal;
  invested: Decimal;
  unrealized_pnl: Decimal;
  realized_pnl: Decimal;
  total_return_pct: Decimal;
  return_12m_pct: Decimal;
  day_change: Decimal;
  day_change_pct: Decimal;
  dividends_12m: Decimal;
  dividends_total: Decimal;
  dividends_receivable: Decimal;
  warnings: SourceWarning[];
}

export interface EquityPoint {
  date: ISODate;
  equity: Decimal;
  invested: Decimal;
}

/** Cumulative returns since the start of the selected window, in percentage points. */
export interface ReturnPoint {
  date: ISODate;
  portfolio_pct: Decimal;
  ibov_pct: Decimal | null;
  cdi_pct: Decimal | null;
}

export type PendingKind = "BONUS_NO_COST" | "POSSIBLE_DUPLICATE" | "UNRECOGNIZED_EVENT";

export interface PendingItem {
  id: string;
  kind: PendingKind;
  ticker: string;
  date: ISODate;
  message: string;
  transaction_id: number | null;
}

export interface Transaction {
  id: number;
  date: ISODate;
  ticker: string;
  type: TransactionType;
  quantity: Decimal;
  price: Decimal | null;
  costs: Decimal | null;
  /** SPLIT / REVERSE_SPLIT / TICKER_CHANGE conversion factor. */
  factor: Decimal | null;
  /** TICKER_CHANGE destination. */
  target_ticker: string | null;
  broker: string | null;
  note: string | null;
  source: Source;
  possible_duplicate: boolean;
  user_edited: boolean;
  /** Gross / tax / net for DIVIDEND, JCP, INCOME. */
  gross_amount: Decimal | null;
  tax_withheld: Decimal | null;
  net_amount: Decimal | null;
}

export interface TransactionInput {
  date: ISODate;
  ticker: string;
  type: TransactionType;
  quantity: Decimal;
  price?: Decimal | null;
  costs?: Decimal | null;
  factor?: Decimal | null;
  target_ticker?: string | null;
  broker?: string | null;
  note?: string | null;
}

export interface TransactionFilters {
  ticker?: string;
  type?: TransactionType | "ALL";
  source?: Source | "ALL";
  from?: ISODate;
  to?: ISODate;
}

export interface ValidationIssue {
  field: string;
  message: string;
  severity: "error" | "warning";
}

export interface Dividend {
  id: number;
  ticker: string;
  asset_class: AssetClass;
  type: DividendType;
  status: DividendStatus;
  ex_date: ISODate;
  pay_date: ISODate | null;
  quantity: Decimal;
  amount_per_share: Decimal;
  gross: Decimal;
  tax: Decimal;
  net: Decimal;
  source: Source;
}

export interface AssetSearchResult {
  ticker: string;
  name: string;
  asset_class: AssetClass;
}

export type IndicatorStatus = "GOOD" | "MID" | "BAD" | "NA";
export type IndicatorUnit = "pct" | "x" | "brl" | "ratio" | "count";

export interface Indicator {
  key: string;
  label: string;
  group: "QUALITY" | "PRICE";
  value: Decimal | null;
  unit: IndicatorUnit;
  /** Human description of the scoring range, e.g. "8% → 20%". */
  range_label: string;
  points: Decimal | null;
  max_points: Decimal;
  status: IndicatorStatus;
  note: string | null;
}

export type SpecialSector = "FINANCIAL" | "UTILITY" | "CYCLICAL";

export interface EliminatoryCheck {
  id: string;
  label: string;
  rule: string;
  value_label: string | null;
  passed: boolean | null;
}

/** Inputs of the Graham fair price and the Bazin ceiling (shown step by step). */
export interface Valuation {
  /** LPA TTM = net_income_ttm / shares */
  eps: Decimal | null;
  /** VPA = equity / shares */
  bvps: Decimal | null;
  net_income_ttm: Decimal | null;
  equity: Decimal | null;
  shares: Decimal | null;
  graham_note: string | null;
  /** Average of dps_by_year; null when the CVM/B3 cross-check fails. */
  dps_5y: Decimal | null;
  dps_note: string | null;
  dps_by_year: { year: number; dps: Decimal }[];
}

/** Any computed indicator, scored or not (indicator panel). Percentages in points. */
export interface FundamentalValue {
  key: string;
  label: string;
  value: Decimal | null;
  unit: IndicatorUnit;
  note: string | null;
}

/**
 * One column of the indicator history: a fiscal year or the trailing 12 months ("12M").
 * Per-share figures use the current share count; past multiples use the December close (split-adjusted).
 * Percentages in points.
 */
export interface YearFigures {
  label: string;
  year: number | null;
  period_end: ISODate;
  revenue: Decimal | null;
  ebit: Decimal | null;
  ebitda: Decimal | null;
  net_income: Decimal | null;
  equity: Decimal | null;
  net_debt: Decimal | null;
  dividends_paid: Decimal | null;
  operating_cash_flow: Decimal | null;
  capex: Decimal | null;
  eps: Decimal | null;
  bvps: Decimal | null;
  dps: Decimal | null;
  net_margin_pct: Decimal | null;
  ebit_margin_pct: Decimal | null;
  roe_pct: Decimal | null;
  roic_pct: Decimal | null;
  net_debt_ebitda: Decimal | null;
  current_ratio: Decimal | null;
  payout_pct: Decimal | null;
  price: Decimal | null;
  pe: Decimal | null;
  pb: Decimal | null;
  dy_pct: Decimal | null;
}

/** Chart analysis (F8): price vs. the 200-day SMA (daily, split-adjusted). Percentages in points. */
export interface TechnicalAnalysis {
  /** 0–100; null when there is not enough history (the price score uses the fundamentals only). */
  score: number | null;
  sma: Decimal | null;
  /** Price above (+) or below (−) the SMA, in %. */
  distance_pct: Decimal | null;
  price: Decimal | null;
  sessions: number;
  sma_days: number;
  /** Distance that scores 100 (e.g. −10). */
  cheap_pct: Decimal;
  /** Distance that scores 0 (e.g. +10). */
  expensive_pct: Decimal;
  note: string | null;
}

export interface AssetAnalysis {
  ticker: string;
  name: string;
  sector: string | null;
  special_sector: SpecialSector | null;
  asset_class: AssetClass;
  price: Decimal | null;
  price_date: ISODate | null;
  day_change_pct: Decimal | null;
  fundamentals_ref: string | null;
  fundamentals_date: ISODate | null;
  decision: Decision;
  score_final: number | null;
  score_quality: number | null;
  score_price: number | null;
  quality_inconclusive: boolean;
  price_inconclusive: boolean;
  /** Statements too old: both scores inconclusive. */
  stale: boolean;
  /** Price score before the technical component (F8) and the loss cap. */
  score_price_fundamental: number | null;
  score_technical: number | null;
  technical_weight: number;
  /** Null when the chart analysis is disabled or for asset classes without rules. */
  technical: TechnicalAnalysis | null;
  eliminatory: EliminatoryCheck[];
  indicators: Indicator[];
  /** Every computed indicator (scored or not); empty for asset classes without rules. */
  fundamentals: FundamentalValue[];
  /** Oldest year first; "12M" last when there is a quarterly statement after the last DFP. */
  history: YearFigures[];
  graham_fair_price: Decimal | null;
  graham_margin_pct: Decimal | null;
  bazin_ceiling: Decimal | null;
  dy_5y_pct: Decimal | null;
  /** Null for asset classes without rules. */
  valuation: Valuation | null;
  warnings: SourceWarning[];
}

export interface PriceBar {
  time: ISODate;
  open: Decimal;
  high: Decimal;
  low: Decimal;
  close: Decimal;
  volume: Decimal;
}

export type ImportFileKind = "NEGOTIATION" | "MOVEMENT";
export type ImportRowStatus = "NEW" | "DUPLICATE" | "IGNORED" | "ERROR";

export interface ImportPreviewRow {
  line: number;
  date: ISODate | null;
  ticker: string | null;
  kind: string;
  mapped_type: TransactionType | null;
  quantity: Decimal | null;
  price: Decimal | null;
  value: Decimal | null;
  broker: string | null;
  status: ImportRowStatus;
  reason: string | null;
}

export interface ImportPreview {
  id: string;
  file_name: string;
  file_kind: ImportFileKind;
  rows: ImportPreviewRow[];
  counts: Record<ImportRowStatus, number>;
}

export interface ImportResult {
  inserted: number;
  duplicates: number;
  ignored: number;
  errors: number;
}

/** An independent portfolio (its own database on the backend). */
export interface Profile {
  id: string;
  name: string;
  primary: boolean;
  discord: boolean; // daily report and watchlist alert (first profile only)
}

export interface ReportPreview {
  date: ISODate;
  content: string; // Discord-flavoured Markdown, as sent
  messages: string[];
  configured: boolean;
  report_time: string;
  last_scheduled: ISODate | null;
}

/** Watchlist (alerted on Discord only by the price against the SMA200). */
export type SmaZone = "CHEAP" | "BELOW" | "ABOVE" | "EXPENSIVE";

export interface WatchItem {
  ticker: string;
  name: string | null;
  note: string | null;
  price: Decimal | null;
  sma: Decimal | null;
  distance_pct: Decimal | null; // percentage points: price / SMA − 1
  zone: SmaZone | null; // null → less history than the SMA needs
  sessions: number;
  price_date: ISODate | null;
}

export interface Watchlist {
  items: WatchItem[];
  channel: "SEPARATE" | "SHARED" | null;
  report_time: string;
  sma_days: number;
  cheap_pct: Decimal; // e.g. "-10"
  expensive_pct: Decimal;
  last_scheduled: ISODate | null;
}

export interface WatchlistPreview {
  date: ISODate;
  content: string;
  messages: string[];
  channel: Watchlist["channel"];
}

export interface ReportDispatch {
  id: number;
  report_date: ISODate;
  trigger: "SCHEDULED" | "MANUAL";
  status: "SENT" | "FAILED";
  late: boolean;
  channel: string;
  messages: number;
  error: string | null;
  created_at: ISODateTime;
}
