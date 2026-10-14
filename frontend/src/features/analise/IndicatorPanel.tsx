import type { AssetAnalysis, FundamentalValue, Indicator } from "@/api/types";
import { Panel, PanelHeader } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { INDICATOR_TERMS, TERMS } from "./glossary";
import { STATUS, Tip, formatValue } from "./shared";

/** Short card labels (the long ones are in the "i" and in the rules tables). */
const LABELS: Record<string, string> = {
  dy_12m: "DY 12M",
  dy_5y: "DY médio 5A",
  pe: "P/L",
  pb: "P/VP",
  ev_ebitda: "EV/EBITDA",
  ev_ebit: "EV/EBIT",
  p_ebit: "P/EBIT",
  psr: "P/Receita (PSR)",
  p_assets: "P/Ativo",
  fcf_yield: "FCF yield",
  eps: "LPA",
  bvps: "VPA",
  pe_norm: "P/L (lucro médio 5A)",
  ev_ebit_norm: "EV/EBIT (EBIT médio 5A)",
  net_debt_equity: "Dív. líquida / PL",
  net_debt_ebitda: "Dív. líquida / EBITDA",
  net_debt_ebitda_norm: "Dív. líq. / EBITDA médio 5A",
  net_debt_ebit: "Dív. líquida / EBIT",
  liabilities_assets: "Passivo / Ativo",
  equity_to_assets: "PL / Ativo",
  current_ratio: "Liquidez corrente",
  ebitda_margin: "Margem EBITDA",
  ebit_margin: "Margem EBIT",
  net_margin: "Margem líquida",
  net_margin_5y: "Margem líquida média 5A",
  cash_conversion_5y: "FCO / Lucro 5A",
  roe: "ROE",
  roe_5y: "ROE médio 5A",
  roic: "ROIC",
  roa: "ROA",
  asset_turnover: "Giro do ativo",
  cagr_revenue_5y: "CAGR receita 5A",
  cagr_earnings_5y: "CAGR lucro 5A",
  cagr_book_5y: "CAGR patrimônio 5A",
  earnings_drops_5y: "Quedas de lucro 5A",
  payout_5y: "Payout médio 5A",
  dps_12m: "Proventos / ação 12M",
  dps_5y: "Proventos / ação médio 5A",
  market_cap: "Valor de mercado",
  ev: "Valor da firma",
  net_debt: "Dívida líquida",
  revenue_ttm: "Receita 12M",
  ebitda_ttm: "EBITDA 12M",
  net_income_ttm: "Lucro 12M",
  daily_liquidity: "Liquidez diária",
};

const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Valuation", keys: ["dy_12m", "dy_5y", "pe", "pb", "ev_ebitda", "ev_ebit", "p_ebit", "psr", "p_assets", "fcf_yield", "pe_norm", "ev_ebit_norm", "eps", "bvps"] },
  { title: "Endividamento", keys: ["net_debt_equity", "net_debt_ebitda", "net_debt_ebitda_norm", "net_debt_ebit", "liabilities_assets", "equity_to_assets", "current_ratio"] },
  { title: "Eficiência", keys: ["ebitda_margin", "ebit_margin", "net_margin", "net_margin_5y", "cash_conversion_5y"] },
  { title: "Rentabilidade", keys: ["roe", "roe_5y", "roic", "roa", "asset_turnover"] },
  { title: "Crescimento e dividendos", keys: ["cagr_revenue_5y", "cagr_earnings_5y", "cagr_book_5y", "earnings_drops_5y", "payout_5y", "dps_12m", "dps_5y"] },
  { title: "Tamanho e liquidez", keys: ["market_cap", "ev", "net_debt", "revenue_ttm", "ebitda_ttm", "net_income_ttm", "daily_liquidity"] },
];

/** Banks and insurers: cash flows, "revenue" and EBIT-based figures do not mean the same thing (CLAUDE.md §5.4). */
const NOT_FOR_BANKS = new Set(["fcf_yield", "psr", "p_assets", "ev_ebitda", "ev_ebit", "p_ebit", "ev", "ebitda_margin", "ebit_margin", "asset_turnover", "cash_conversion_5y", "ebitda_ttm"]);

function Tile({ f, scored }: { f: FundamentalValue; scored?: Indicator }) {
  const status = scored && Number(scored.max_points) > 0 ? STATUS[scored.status] : null;
  const term = INDICATOR_TERMS[f.key];
  const Icon = status?.icon;
  const decimals = f.unit === "count" ? 0 : 2;
  return (
    <div className="flex min-w-0 flex-col rounded-md border border-line bg-surface-2 px-3 py-2.5">
      <dt className="flex min-w-0 items-center gap-1 text-sm text-ink-2">
        <span className="truncate">{LABELS[f.key] ?? f.label}</span>
        {term && <Tip term={term} />}
      </dt>
      <dd className={cn("num mt-1 text-xl font-semibold tracking-tight", f.value === null && "text-muted")}>
        {formatValue(f.value, f.unit, decimals)}
      </dd>
      {status && Icon ? (
        <dd className={cn("mt-auto flex items-center gap-1 pt-1 text-xs font-medium", status.className)}>
          <Icon className="size-3.5" aria-hidden /> {status.label} na nota
        </dd>
      ) : (
        f.value === null &&
        f.note && (
          <dd className="mt-auto truncate pt-1 text-xs text-muted" title={f.note}>
            {f.note}
          </dd>
        )
      )}
    </div>
  );
}

/** Every indicator, grouped like a stock site: valuation, debt, efficiency, profitability, growth, size. */
export function IndicatorPanel({ a }: { a: AssetAnalysis }) {
  const byKey = new Map(a.fundamentals.map((f) => [f.key, f]));
  const scored = new Map(a.indicators.map((i) => [i.key, i]));
  const financial = a.special_sector === "FINANCIAL";
  const cyclical = a.special_sector === "CYCLICAL";
  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.keys.flatMap((key) => {
      const f = byKey.get(key);
      if (!f) return [];
      // Multiples over 5-year averages only matter for cyclicals (where the rules use them)
      if (key.endsWith("_norm") && !cyclical) return [];
      if (financial && NOT_FOR_BANKS.has(key)) return [];
      // Missing values only matter when they explain something (banks have no EBITDA, net debt…)
      if (f.value === null && !scored.has(key) && (financial || !f.note)) return [];
      return [f];
    }),
  })).filter((g) => g.items.length > 0);

  return (
    <Panel id="indicadores" className="scroll-mt-20">
      <PanelHeader
        title={
          <span className="flex items-center gap-1.5">
            Indicadores fundamentalistas <Tip term={TERMS.panel} />
          </span>
        }
        description="Últimos 12 meses e último balanço, com a cotação atual. Os que entram na nota mostram o status."
      />
      <div className="flex flex-col gap-5 px-4 pb-4">
        {groups.map((g) => (
          <section key={g.title} aria-label={g.title}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{g.title}</h3>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {g.items.map((f) => (
                <Tile key={f.key} f={f} scored={scored.get(f.key)} />
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Panel>
  );
}
