/** In-memory mock backend so every screen is interactive before the API exists. */
import type {
  ImportResult,
  Transaction,
  TransactionFilters,
  TransactionInput,
  ValidationIssue,
} from "@/api/types";
import { ApiError } from "@/api/client";
import {
  SEARCH_UNIVERSE,
  buildAnalysis,
  buildDividends,
  buildEquitySeries,
  buildImportPreview,
  buildPending,
  buildPositions,
  buildPriceBars,
  buildReturnSeries,
  buildSummary,
  buildTransactions,
} from "./data";

const LATENCY_MS = 220;
const wait = <T>(value: T): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));

let transactions: Transaction[] | null = null;
let nextId = 50_000;

function ledger(): Transaction[] {
  transactions ??= buildTransactions();
  return transactions;
}

function positionOn(ticker: string, date: string, ignoreId?: number): number {
  let qty = 0;
  const rows = ledger()
    .filter((t) => t.ticker === ticker && t.date <= date && t.id !== ignoreId)
    .sort((a, b) => a.date.localeCompare(b.date));
  for (const t of rows) {
    const q = Number(t.quantity);
    if (t.type === "BUY" || t.type === "BONUS" || t.type === "SPLIT") qty += q;
    else if (t.type === "SELL") qty -= q;
    else if (t.type === "REVERSE_SPLIT") qty = q;
  }
  return qty;
}

function validate(input: TransactionInput, ignoreId?: number): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!input.ticker) issues.push({ field: "ticker", message: "Informe o ticker.", severity: "error" });
  const qty = Number(input.quantity);
  if (!(qty > 0)) issues.push({ field: "quantity", message: "A quantidade deve ser maior que zero.", severity: "error" });
  if ((input.type === "BUY" || input.type === "SELL") && !(Number(input.price) > 0))
    issues.push({ field: "price", message: "Informe o preço unitário.", severity: "error" });
  if (input.type === "SELL" && input.ticker) {
    const held = positionOn(input.ticker, input.date, ignoreId);
    if (qty > held)
      issues.push({
        field: "quantity",
        message: `Você tinha ${held} ${input.ticker} em ${input.date.split("-").reverse().join("/")}. Não é possível vender ${qty}.`,
        severity: "error",
      });
  }
  return issues;
}

function toTransaction(input: TransactionInput, id: number): Transaction {
  return {
    id,
    date: input.date,
    ticker: input.ticker.toUpperCase().replace(/F$/, ""),
    type: input.type,
    quantity: input.quantity,
    price: input.price ?? null,
    costs: input.costs ?? null,
    factor: input.factor ?? null,
    target_ticker: input.target_ticker ?? null,
    broker: input.broker ?? null,
    note: input.note ?? null,
    source: "MANUAL",
    possible_duplicate: false,
    user_edited: false,
    gross_amount: null,
    tax_withheld: null,
    net_amount: null,
  };
}

export const mockServer = {
  summary: () => wait(buildSummary()),
  positions: () => wait(buildPositions()),
  pending: () => wait(buildPending()),
  equitySeries: () => wait(buildEquitySeries()),
  returnSeries: () => wait(buildReturnSeries()),
  dividends: () => wait(buildDividends()),

  transactions: (filters: TransactionFilters = {}) =>
    wait(
      ledger().filter(
        (t) =>
          (!filters.ticker || t.ticker.includes(filters.ticker.toUpperCase())) &&
          (!filters.type || filters.type === "ALL" || t.type === filters.type) &&
          (!filters.source || filters.source === "ALL" || t.source === filters.source) &&
          (!filters.from || t.date >= filters.from) &&
          (!filters.to || t.date <= filters.to),
      ),
    ),

  createTransaction: async (input: TransactionInput) => {
    const issues = validate(input);
    if (issues.some((i) => i.severity === "error")) {
      await wait(null);
      throw new ApiError(422, issues[0].message, issues);
    }
    const tx = toTransaction(input, nextId++);
    ledger().unshift(tx);
    return wait(tx);
  },

  createTransactionsBatch: async (inputs: TransactionInput[]) => {
    const all: ValidationIssue[] = [];
    inputs.forEach((input, index) =>
      validate(input).forEach((issue) => all.push({ ...issue, field: `${index}.${issue.field}` })),
    );
    if (all.some((i) => i.severity === "error")) {
      await wait(null);
      throw new ApiError(422, "Há linhas com erro. Corrija antes de salvar.", all);
    }
    const created = inputs.map((input) => toTransaction(input, nextId++));
    ledger().unshift(...created);
    return wait(created);
  },

  updateTransaction: async (id: number, input: TransactionInput) => {
    const issues = validate(input, id);
    if (issues.some((i) => i.severity === "error")) {
      await wait(null);
      throw new ApiError(422, issues[0].message, issues);
    }
    const rows = ledger();
    const index = rows.findIndex((t) => t.id === id);
    if (index < 0) throw new ApiError(404, "Lançamento não encontrado.");
    rows[index] = { ...toTransaction(input, id), source: rows[index].source, user_edited: rows[index].source === "AUTO" };
    return wait(rows[index]);
  },

  deleteTransaction: async (id: number) => {
    transactions = ledger().filter((t) => t.id !== id);
    return wait(undefined);
  },

  searchAssets: (q: string) => {
    const query = q.trim().toUpperCase();
    if (!query) return wait(SEARCH_UNIVERSE.slice(0, 8));
    return wait(
      SEARCH_UNIVERSE.filter((a) => a.ticker.includes(query) || a.name.toUpperCase().includes(query)).slice(0, 8),
    );
  },

  analysis: async (ticker: string) => {
    const result = buildAnalysis(ticker.toUpperCase());
    if (!result) {
      await wait(null);
      throw new ApiError(404, `Não encontramos ${ticker.toUpperCase()} na B3.`);
    }
    return wait(result);
  },

  priceBars: (ticker: string) => wait(buildPriceBars(ticker.toUpperCase())),

  refreshPrices: () => wait({ updated: 12, failed: 0 }),

  importPreview: (file: File) => wait(buildImportPreview(file.name)),

  importCommit: (previewId: string): Promise<ImportResult> => {
    void previewId;
    return wait({ inserted: 4, duplicates: 2, ignored: 3, errors: 1 });
  },
};
