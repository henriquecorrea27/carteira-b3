import * as React from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AssetAnalysis, IndicatorUnit, YearFigures } from "@/api/types";
import { ChartTooltipBox, Legend, axisProps, gridProps, type TooltipRow } from "@/components/charts/common";
import { Panel, PanelHeader } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatNumber, formatPct, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { INDICATOR_TERMS, TERMS, type Term } from "./glossary";
import { Tip, formatBigBRL, formatValue } from "./shared";

const C1 = "var(--series-1)";
const C2 = "var(--series-2)";
const C3 = "var(--series-3)";

const num = (v: string | null) => toNumber(v);
const yearTitle = (label: string) => (label === "12M" ? "Últimos 12 meses" : `Ano de ${label}`);

/** Axis money: R$ 42 bi · R$ 350 mi */
function axisBRL(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1e9) return `${sign}R$ ${formatNumber(abs / 1e9, { maxDecimals: 1 })} bi`;
  if (abs >= 1e6) return `${sign}R$ ${formatNumber(abs / 1e6, { maxDecimals: 0 })} mi`;
  if (abs >= 1e3) return `${sign}R$ ${formatNumber(abs / 1e3, { maxDecimals: 0 })} mil`;
  return `${sign}R$ ${formatNumber(abs, { maxDecimals: 2 })}`;
}

const pctAxis = (n: number) => `${formatNumber(n, { maxDecimals: 0 })}%`;

function ChartBox({ height = 240, children }: { height?: number; children: React.ReactElement }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

/** Revenue and net income by year: two series in R$, one axis. */
function ResultsChart({ history }: { history: YearFigures[] }) {
  const data = history.map((h) => ({ label: h.label, revenue: num(h.revenue), net_income: num(h.net_income), h }));
  const hasLoss = data.some((d) => (d.net_income ?? 0) < 0);
  return (
    <Panel>
      <PanelHeader title="Receita e lucro líquido" description="Por ano fiscal e nos últimos 12 meses (12M)." />
      <div className="px-4 pb-4">
        <Legend
          className="mb-3"
          items={[
            { label: "Receita líquida", color: C1, shape: "bar" },
            { label: "Lucro líquido", color: C2, shape: "bar" },
          ]}
        />
        <ChartBox>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%" barGap={3}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} dy={6} />
            <YAxis tickFormatter={axisBRL} {...axisProps} width={78} />
            {hasLoss && <ReferenceLine y={0} stroke="var(--line-strong)" />}
            <Tooltip
              cursor={{ fill: "var(--sunken)", opacity: 0.7 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const { h } = payload[0].payload as (typeof data)[number];
                return (
                  <ChartTooltipBox
                    title={yearTitle(h.label)}
                    rows={[
                      { key: "r", label: "Receita líquida", value: formatBigBRL(h.revenue), color: C1, shape: "bar" },
                      { key: "l", label: "Lucro líquido", value: formatBigBRL(h.net_income), color: C2, shape: "bar" },
                    ]}
                    footer={`Margem líquida ${formatPct(h.net_margin_pct, { decimals: 1 })}`}
                  />
                );
              }}
            />
            <Bar dataKey="revenue" fill={C1} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            <Bar dataKey="net_income" fill={C2} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          </BarChart>
        </ChartBox>
      </div>
    </Panel>
  );
}

const MARGIN_SERIES: { key: "net_margin_pct" | "ebit_margin_pct" | "roe_pct"; label: string; color: string }[] = [
  { key: "roe_pct", label: "ROE", color: C1 },
  { key: "ebit_margin_pct", label: "Margem EBIT", color: C2 },
  { key: "net_margin_pct", label: "Margem líquida", color: C3 },
];

/** Profitability and margins by year: all in %, one axis. */
function MarginsChart({ history }: { history: YearFigures[] }) {
  const series = MARGIN_SERIES.filter((s) => history.some((h) => h[s.key] !== null));
  const data = history.map((h) => ({ label: h.label, ...Object.fromEntries(series.map((s) => [s.key, num(h[s.key])])), h }));
  const hasNegative = data.some((d) => series.some((s) => ((d as Record<string, unknown>)[s.key] as number | null ?? 0) < 0));
  if (series.length === 0) return null;
  return (
    <Panel>
      <PanelHeader title="Rentabilidade e margens" description="ROE sobre o patrimônio médio do ano; margens sobre a receita." />
      <div className="px-4 pb-4">
        <Legend className="mb-3" items={series.map((s) => ({ label: s.label, color: s.color }))} />
        <ChartBox>
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} dy={6} padding={{ left: 12, right: 12 }} />
            <YAxis tickFormatter={pctAxis} {...axisProps} width={44} />
            {hasNegative && <ReferenceLine y={0} stroke="var(--line-strong)" />}
            <Tooltip
              cursor={{ stroke: "var(--line-strong)", strokeWidth: 1 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const { h } = payload[0].payload as { h: YearFigures };
                return (
                  <ChartTooltipBox
                    title={yearTitle(h.label)}
                    rows={series.map((s) => ({ key: s.key, label: s.label, value: formatPct(h[s.key], { decimals: 1 }), color: s.color }))}
                  />
                );
              }}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                dot={{ r: 4, fill: s.color, stroke: "var(--surface)", strokeWidth: 2 }}
                activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ChartBox>
      </div>
    </Panel>
  );
}

function SingleBars({
  data,
  color,
  format,
  axisFormat,
  name,
}: {
  data: { label: string; value: number | null; h: YearFigures }[];
  color: string;
  format: (h: YearFigures) => TooltipRow[];
  axisFormat: (n: number) => string;
  name: string;
}) {
  return (
    <ChartBox height={220}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap="28%" accessibilityLayer>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="label" {...axisProps} dy={6} />
        <YAxis tickFormatter={axisFormat} {...axisProps} width={60} />
        <Tooltip
          cursor={{ fill: "var(--sunken)", opacity: 0.7 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const { h } = payload[0].payload as { h: YearFigures };
            return <ChartTooltipBox title={yearTitle(h.label)} rows={format(h)} />;
          }}
        />
        <Bar dataKey="value" name={name} fill={color} radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
      </BarChart>
    </ChartBox>
  );
}

function MiniStat({ label, term, value, sub }: { label: string; term?: Term; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-sm text-ink-2">
        {label}
        {term && <Tip term={term} />}
      </dt>
      <dd className="num mt-0.5 text-xl font-semibold tracking-tight">{value}</dd>
      {sub && <dd className="text-xs text-muted">{sub}</dd>}
    </div>
  );
}

/** Dividends per share and dividend yield by year (two charts: different units never share an axis). */
function DividendsPanel({ a }: { a: AssetAnalysis }) {
  const history = a.history.filter((h) => h.dps !== null);
  if (history.length === 0) return null;
  const f = (key: string) => a.fundamentals.find((x) => x.key === key) ?? null;
  const payout = a.indicators.find((i) => i.key === "payout_5y") ?? f("payout_5y");
  const dps = history.map((h) => ({ label: h.label, value: num(h.dps), h }));
  const dy = history.map((h) => ({ label: h.label, value: num(h.dy_pct), h }));
  const rows = (h: YearFigures): TooltipRow[] => [
    { key: "d", label: "por ação", value: formatBRL(h.dps, { precise: true }), color: C1, shape: "bar" },
    { key: "y", label: h.year === null ? "DY no preço atual" : "DY no fechamento de dez.", value: formatPct(h.dy_pct, { decimals: 2 }), color: C3, shape: "bar" },
    { key: "p", label: "payout", value: formatPct(h.payout_pct, { decimals: 0 }), color: "transparent" },
  ];
  return (
    <Panel id="dividendos" className="scroll-mt-20">
      <PanelHeader
        title={
          <span className="flex items-center gap-1.5">
            Dividendos <Tip term={TERMS.dps} />
          </span>
        }
        description="Dividendos + JCP pagos em cada ano (fluxo de caixa da CVM) ÷ número de ações atual."
      />
      <div className="px-4 pb-4">
        <dl className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MiniStat label="DY 12 meses" term={INDICATOR_TERMS.dy_12m} value={formatValue(f("dy_12m")?.value ?? null, "pct")} />
          <MiniStat label="DY médio 5 anos" term={INDICATOR_TERMS.dy_5y} value={formatPct(a.dy_5y_pct, { decimals: 2 })} />
          <MiniStat label="Payout médio 5 anos" term={INDICATOR_TERMS.payout_5y} value={formatValue(payout?.value ?? null, "pct", 0)} />
          <MiniStat
            label="Preço teto Bazin"
            term={TERMS.bazin}
            value={formatBRL(a.bazin_ceiling)}
            sub={a.valuation?.dps_5y ? `média ${formatBRL(a.valuation.dps_5y, { precise: true })} ÷ 6%` : undefined}
          />
        </dl>
        <div className="grid gap-6 lg:grid-cols-2">
          <section aria-label="Proventos por ação por ano">
            <h3 className="mb-2 text-sm font-medium text-ink-2">Proventos por ação (R$)</h3>
            <SingleBars data={dps} color={C1} name="Proventos por ação" format={rows} axisFormat={(n) => formatBRL(n)} />
          </section>
          <section aria-label="Dividend yield por ano">
            <h3 className="mb-2 text-sm font-medium text-ink-2">Dividend yield (proventos ÷ cotação de dezembro)</h3>
            <SingleBars data={dy} color={C3} name="Dividend yield" format={rows} axisFormat={pctAxis} />
          </section>
        </div>
      </div>
    </Panel>
  );
}

type Row = { label: string; key: keyof YearFigures; unit: IndicatorUnit; term?: Term };

/** The few ratios worth following year by year (the amounts in R$ are in the charts above). */
const ROWS: Row[] = [
  { label: "P/L", key: "pe", unit: "x", term: INDICATOR_TERMS.pe },
  { label: "P/VP", key: "pb", unit: "x", term: INDICATOR_TERMS.pb },
  { label: "Dividend yield", key: "dy_pct", unit: "pct", term: INDICATOR_TERMS.dy_12m },
  { label: "ROE", key: "roe_pct", unit: "pct", term: INDICATOR_TERMS.roe },
  { label: "ROIC", key: "roic_pct", unit: "pct", term: INDICATOR_TERMS.roic },
  { label: "Margem líquida", key: "net_margin_pct", unit: "pct", term: INDICATOR_TERMS.net_margin },
  { label: "Dív. líquida / EBITDA", key: "net_debt_ebitda", unit: "x", term: INDICATOR_TERMS.net_debt_ebitda },
  { label: "LPA", key: "eps", unit: "brl", term: INDICATOR_TERMS.eps },
  { label: "Proventos por ação", key: "dps", unit: "brl", term: TERMS.dps },
  { label: "Payout", key: "payout_pct", unit: "pct", term: INDICATOR_TERMS.payout_5y },
];

/** Banks and insurers: ROIC and EBITDA do not mean the same as in other companies. */
const BANK_HIDDEN = new Set<keyof YearFigures>(["roic_pct", "net_debt_ebitda"]);

/** 1 decimal for ratios and percentages, cents for amounts per share. */
function cell(value: string | number | null, unit: IndicatorUnit): string {
  return formatValue(value, unit, unit === "brl" ? 2 : 1);
}

/** Average of the last 5 closed years (at least 3 with data), like the "médio 5a" indicators of the rules. */
function avg5(history: YearFigures[], key: keyof YearFigures): number | null {
  const values = history
    .filter((h) => h.year !== null)
    .map((h) => toNumber(h[key] as string | null))
    .filter((v): v is number => v !== null);
  return values.length >= 3 ? values.reduce((s, v) => s + v, 0) / values.length : null;
}

/** Latest value: the last 12 months when there is a quarterly report, else the last fiscal year. */
function latest(history: YearFigures[], key: keyof YearFigures): { value: string | null; label: string } {
  for (let i = history.length - 1; i >= 0; i--) {
    const v = history[i][key] as string | null;
    if (v !== null) return { value: v, label: history[i].label };
  }
  return { value: null, label: "" };
}

function Sparkline({ history, row }: { history: YearFigures[]; row: Row }) {
  const data = history.map((h) => ({ label: h.label, value: num(h[row.key] as string | null), h }));
  if (data.filter((d) => d.value !== null).length < 2) return null;
  return (
    <div className="h-10 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip
            cursor={{ stroke: "var(--line-strong)", strokeWidth: 1 }}
            allowEscapeViewBox={{ x: true, y: true }}
            wrapperStyle={{ zIndex: 20 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const { h } = payload[0].payload as { h: YearFigures };
              return <ChartTooltipBox title={yearTitle(h.label)} rows={[{ key: "v", label: row.label, value: cell(h[row.key] as string | null, row.unit), color: C1 }]} />;
            }}
          />
          <Line
            dataKey="value"
            stroke={C1}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: C1, stroke: "var(--surface-2)", strokeWidth: 2 }}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** One tile per ratio: the latest value, the 5-year average and the trend line. */
function TrendTiles({ history, rows }: { history: YearFigures[]; rows: Row[] }) {
  return (
    <dl className="grid grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-3 xl:grid-cols-5">
      {rows.map((r) => {
        const last = latest(history, r.key);
        const n = toNumber(last.value);
        return (
          <div key={r.key} className="flex min-w-0 flex-col rounded-md border border-line bg-surface-2 px-3 py-2.5">
            <dt className="flex min-w-0 items-center gap-1 text-sm text-ink-2">
              <span className="truncate">{r.label}</span>
              {r.term && <Tip term={r.term} />}
            </dt>
            <dd className={cn("num mt-1 whitespace-nowrap text-xl font-semibold tracking-tight", n !== null && n < 0 && "text-down")}>
              {cell(last.value, r.unit)}
              {last.label && <span className="ml-1.5 text-xs font-normal text-muted">{last.label}</span>}
            </dd>
            <dd className="num whitespace-nowrap text-xs text-muted">média 5A {cell(avg5(history, r.key), r.unit)}</dd>
            <dd className="mt-auto pt-1">
              <Sparkline history={history} row={r} />
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

/** The same ratios as a year-by-year table (the accessible view of the trend lines). */
function YearTable({ history, rows }: { history: YearFigures[]; rows: Row[] }) {
  const sticky = "sticky left-0 z-[1] bg-surface";
  return (
    <Table className="text-sm">
      <THead>
        <TR className="bg-surface-2">
          <TH className={cn(sticky, "bg-surface-2")}>Indicador</TH>
          {history.map((h) => (
            <TH key={h.label} numeric>
              {h.label === "12M" ? (
                <span className="inline-flex items-center gap-1">
                  12M <Tip term={TERMS.ttm} side="bottom" />
                </span>
              ) : (
                h.label
              )}
            </TH>
          ))}
          <TH numeric className="border-l border-line">
            <span className="inline-flex items-center gap-1">
              Média 5A <Tip term={TERMS.avg5y} side="left" />
            </span>
          </TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((r) => (
          <TR key={r.key}>
            <TD className={cn(sticky, "font-medium")}>
              <span className="inline-flex items-center gap-1">
                {r.label}
                {r.term && <Tip term={r.term} side="right" />}
              </span>
            </TD>
            {history.map((h) => {
              const v = h[r.key] as string | null;
              const n = toNumber(v);
              return (
                <TD key={h.label} numeric className={cn("num", v === null && "text-muted", n !== null && n < 0 && "text-down")}>
                  {cell(v, r.unit)}
                </TD>
              );
            })}
            <TD numeric className="num border-l border-line font-semibold">
              {cell(avg5(history, r.key), r.unit)}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/** The key ratios over the last 5 fiscal years and the last 12 months: trend tiles, or a table on demand. */
function HistoryTable({ history: all, financial }: { history: YearFigures[]; financial: boolean }) {
  const [view, setView] = React.useState<"trend" | "table">("trend");
  // Last 5 closed years (the base of the 5-year averages) + the last 12 months
  const years = all.filter((h) => h.year !== null).slice(-5);
  const history = [...years, ...all.filter((h) => h.year === null)];
  const rows = ROWS.filter((r) => !(financial && BANK_HIDDEN.has(r.key)) && history.some((h) => h[r.key] !== null));
  if (rows.length === 0) return null;
  return (
    <Panel id="historico" className="scroll-mt-20">
      <PanelHeader
        title={
          <span className="flex items-center gap-1.5">
            Histórico de indicadores <Tip term={TERMS.history} />
          </span>
        }
        description="Valor mais recente, média dos 5 últimos anos e a tendência ano a ano."
        actions={
          <Segmented
            aria-label="Forma de exibir o histórico"
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: "trend", label: "Tendência" },
              { value: "table", label: "Tabela" },
            ]}
          />
        }
      />
      {view === "trend" ? <TrendTiles history={history} rows={rows} /> : <YearTable history={history} rows={rows} />}
      <p className="px-4 pb-3 text-xs text-muted">
        P/L, P/VP e DY dos anos anteriores usam o fechamento de dezembro e o número de ações atual; o 12M usa o preço atual.
      </p>
    </Panel>
  );
}

/** Results, margins, dividends and the indicator history: everything by year. */
export function HistorySection({ a }: { a: AssetAnalysis }) {
  if (a.history.length === 0) return null;
  return (
    <>
      <div id="resultados" className="grid scroll-mt-20 gap-5 lg:grid-cols-2">
        <ResultsChart history={a.history} />
        <MarginsChart history={a.history} />
      </div>
      <DividendsPanel a={a} />
      <HistoryTable history={a.history} financial={a.special_sector === "FINANCIAL"} />
    </>
  );
}
