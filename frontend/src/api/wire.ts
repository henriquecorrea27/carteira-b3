/**
 * Backend (FastAPI) payloads, mirroring backend/app/schemas. Only endpoints.ts should import this.
 * Percentages are fractions ("0.1234" = 12,34%); money and quantities are decimal strings.
 */
import type { AssetClass, DividendStatus, DividendType, Source, TransactionType } from "./types";

type Dec = string;

export interface Position {
  ticker: string;
  name: string | null;
  asset_class: AssetClass;
  sector: string | null;
  quantity: Dec;
  avg_price: Dec;
  total_cost: Dec;
  realized_result: Dec;
  provents_net: Dec;
  provents_net_12m: Dec;
  provents_receivable_net: Dec;
  pending_bonus_cost: boolean;
  first_date: string | null;
  current_price: Dec | null;
  price_date: string | null;
  day_change_pct: Dec | null;
  market_value: Dec | null;
  open_result: Dec | null;
  open_result_pct: Dec | null;
  weight_pct: Dec | null;
  yield_on_cost_pct: Dec | null;
  rules: RulesSummary | null;
}

export interface RulesSummary {
  decision: "BUY" | "WAIT" | "AVOID";
  score_final: number | null;
  score_quality: number | null;
  score_price: number | null;
  inconclusive: boolean;
  main_reason: string | null;
  date: string;
}

export interface Summary {
  invested: Dec;
  market_value: Dec;
  open_result: Dec;
  open_result_pct: Dec | null;
  realized_result: Dec;
  provents_net_total: Dec;
  provents_net_12m: Dec;
  provents_receivable: Dec;
  total_result: Dec;
  return_total: Dec | null;
  return_12m: Dec | null;
  ibov_12m: Dec | null;
  cdi_12m: Dec | null;
  day_change: Dec | null;
  open_positions: number;
  pending_bonus_cost: number;
  prices_as_of: string | null;
  missing_prices: string[];
}

export interface HistoryPoint {
  date: string;
  invested: Dec;
  market_value: Dec;
  portfolio_return: Dec;
  ibov_return: Dec | null;
  cdi_return: Dec | null;
}

export interface DataSourceStatus {
  source: string;
  ok: boolean;
  message: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
}

export interface Transaction {
  id: number;
  date: string;
  ticker: string;
  type: TransactionType;
  quantity: Dec;
  price: Dec | null;
  costs: Dec;
  factor: Dec | null;
  target_ticker: string | null;
  gross_amount: Dec | null;
  tax_withheld: Dec | null;
  net_amount: Dec | null;
  payment_date: string | null;
  status: DividendStatus | null;
  broker: string | null;
  notes: string | null;
  source: Source;
  user_edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface TransactionIn {
  date: string;
  ticker: string;
  type: TransactionType;
  quantity?: Dec | null;
  price?: Dec | null;
  costs?: Dec | null;
  factor?: Dec | null;
  target_ticker?: string | null;
  broker?: string | null;
  notes?: string | null;
}

export interface Issue {
  code: string;
  message: string;
  row?: number | null;
  field?: string | null;
  transaction_id?: number | null;
}

export interface Provent {
  id: number;
  ticker: string;
  asset_class: AssetClass;
  type: DividendType;
  status: DividendStatus;
  record_date: string;
  payment_date: string | null;
  quantity: Dec;
  value_per_share: Dec | null;
  gross_amount: Dec;
  tax_withheld: Dec;
  net_amount: Dec;
  source: Source;
}

export interface Asset {
  ticker: string;
  name: string | null;
  asset_class: AssetClass;
  class_confirmed: boolean;
  sector: string | null;
}

export interface Refresh {
  prices_inserted: number;
  benchmarks_inserted: number;
  errors: string[];
  tickers_without_data: string[];
}

export interface ImportRow {
  file: string;
  line: number;
  status: "NEW" | "DUPLICATE" | "POSSIBLE_DUPLICATE" | "IGNORED" | "ERROR";
  reason: string | null;
  raw: Record<string, string>;
  merged_lines: number[];
  date: string | null;
  ticker: string | null;
  type: TransactionType | null;
  quantity: Dec | null;
  price: Dec | null;
  factor: Dec | null;
  gross_amount: Dec | null;
  tax_withheld: Dec | null;
  broker: string | null;
}

export interface ImportReport {
  committed: boolean;
  files: Record<string, string>;
  counts: Partial<Record<ImportRow["status"], number>>;
  inserted: number;
  rows: ImportRow[];
}

export interface AgendaItem {
  ticker: string;
  kind: string;
  label: string;
  record_date: string;
  ex_date: string;
  payment_date: string | null;
  value: Dec;
  factor: Dec | null;
  quantity: Dec;
  estimated_net: Dec | null;
  in_ledger: boolean;
}

export interface EventsSync {
  issuers: number;
  events_seen: number;
  errors: string[];
}

export interface Analysis {
  ticker: string;
  name: string;
  cnpj: string;
  sector: string | null;
  special_sector: "FINANCIAL" | "UTILITY" | null;
  price: Dec | null;
  price_date: string | null;
  day_change: Dec | null;
  decision: "BUY" | "WAIT" | "AVOID";
  score_final: number | null;
  score_quality: number | null;
  score_price: number | null;
  quality_inconclusive: boolean;
  price_inconclusive: boolean;
  main_reason: string | null;
  eliminatory: { id: string; label: string; rule: string; value_label: string | null; passed: boolean | null }[];
  indicators: {
    key: string;
    label: string;
    group: "QUALITY" | "PRICE";
    value: Dec | null;
    unit: "pct" | "x" | "brl" | "count";
    range_label: string;
    weight: number;
    points: number | null;
    status: "GOOD" | "MID" | "BAD" | "NA";
    note: string | null;
  }[];
  graham_price: Dec | null;
  graham_margin: Dec | null;
  bazin_price: Dec | null;
  dy_5y: Dec | null;
  market_cap: Dec | null;
  last_dfp: string | null;
  last_itr: string | null;
  received_on: string | null;
  warnings: string[];
  rules_version: number;
}

export interface PriceBar {
  date: string;
  open: Dec | null;
  high: Dec | null;
  low: Dec | null;
  close: Dec;
  volume: Dec | null;
}

export interface PortfolioRun {
  analyzed: string[];
  skipped: string[];
  errors: string[];
}
