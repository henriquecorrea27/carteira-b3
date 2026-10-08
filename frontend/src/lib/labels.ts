import type {
  AssetClass,
  Decision,
  DividendStatus,
  DividendType,
  ImportRowStatus,
  Source,
  TransactionType,
} from "@/api/types";

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  STOCK: "Ações",
  FII: "FIIs",
  ETF: "ETFs",
  BDR: "BDRs",
};

export const ASSET_CLASS_SINGULAR: Record<AssetClass, string> = {
  STOCK: "Ação",
  FII: "FII",
  ETF: "ETF",
  BDR: "BDR",
};

export const ASSET_CLASS_ORDER: AssetClass[] = ["STOCK", "FII", "ETF", "BDR"];

export const DECISION_LABEL: Record<Decision, string> = {
  BUY: "Comprar",
  WAIT: "Aguardar",
  AVOID: "Evitar",
};

export const TX_TYPE_LABEL: Record<TransactionType, string> = {
  BUY: "Compra",
  SELL: "Venda",
  SPLIT: "Desdobramento",
  REVERSE_SPLIT: "Grupamento",
  BONUS: "Bonificação",
  FRACTION_AUCTION: "Leilão de fração",
  TICKER_CHANGE: "Troca de ticker",
  DIVIDEND: "Dividendo",
  JCP: "JCP",
  INCOME: "Rendimento",
};

export const DIVIDEND_TYPE_LABEL: Record<DividendType, string> = {
  DIVIDEND: "Dividendo",
  JCP: "JCP",
  INCOME: "Rendimento",
};

export const DIVIDEND_STATUS_LABEL: Record<DividendStatus, string> = {
  ANNOUNCED: "A receber",
  PAID: "Pago",
  CONFIRMED: "Conferido na B3",
};

export const SOURCE_LABEL: Record<Source, string> = {
  MANUAL: "Manual",
  B3: "B3",
  AUTO: "Automático",
};

export const IMPORT_STATUS_LABEL: Record<ImportRowStatus, string> = {
  NEW: "Novo",
  DUPLICATE: "Duplicado",
  IGNORED: "Ignorado",
  ERROR: "Erro",
};
