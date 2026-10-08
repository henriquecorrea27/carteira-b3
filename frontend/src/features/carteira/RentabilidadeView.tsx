import * as React from "react";
import { useEquitySeries, useReturnSeries, useSummary } from "@/api/hooks";
import type { ReturnPoint } from "@/api/types";
import { EquityChart } from "@/components/charts/EquityChart";
import { ReturnsChart } from "@/components/charts/ReturnsChart";
import { Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { MONTH_LABELS, formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { QueryError, RANGE_OPTIONS, filterByRange, type RangeKey } from "../shared";

interface MonthlyRow {
  year: number;
  months: (number | null)[];
  year_total: number;
  cdi_total: number | null;
}

/** Month-over-month returns from cumulative (TWR) points: last point of each month vs the previous month's. */
export function monthlyReturns(points: ReturnPoint[]): MonthlyRow[] {
  const lastOfMonth = new Map<string, ReturnPoint>();
  for (const p of points) lastOfMonth.set(p.date.slice(0, 7), p);
  const months = [...lastOfMonth.keys()].sort();
  const rows = new Map<number, MonthlyRow>();
  const factor = (v: string | null) => (v === null ? null : 1 + Number(v) / 100);
  let prev: ReturnPoint | null = null;
  for (const m of months) {
    const p = lastOfMonth.get(m)!;
    const year = Number(m.slice(0, 4));
    if (!rows.has(year)) rows.set(year, { year, months: Array(12).fill(null), year_total: 1, cdi_total: 1 });
    const row = rows.get(year)!;
    const cur = factor(p.portfolio_pct)!;
    const base = prev ? factor(prev.portfolio_pct)! : 1;
    const r = cur / base;
    row.months[Number(m.slice(5, 7)) - 1] = (r - 1) * 100;
    row.year_total *= r;
    const cdiCur = factor(p.cdi_pct);
    const cdiBase = prev ? factor(prev.cdi_pct) : 1;
    row.cdi_total = row.cdi_total !== null && cdiCur !== null && cdiBase !== null ? row.cdi_total * (cdiCur / cdiBase) : null;
    prev = p;
  }
  return [...rows.values()]
    .sort((a, b) => b.year - a.year)
    .map((r) => ({ ...r, year_total: (r.year_total - 1) * 100, cdi_total: r.cdi_total === null ? null : (r.cdi_total - 1) * 100 }));
}

function MonthlyTable({ rows }: { rows: MonthlyRow[] }) {
  return (
    <Table className="text-sm">
      <THead>
        <TR>
          <TH>Ano</TH>
          {MONTH_LABELS.map((m) => (
            <TH key={m} numeric className="capitalize">
              {m}
            </TH>
          ))}
          <TH numeric>No ano</TH>
          <TH numeric>CDI</TH>
          <TH numeric>% do CDI</TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((r) => (
          <TR key={r.year}>
            <TD className="font-semibold">{r.year}</TD>
            {r.months.map((v, i) => (
              <TD key={i} numeric className={cn(v === null ? "text-muted" : v >= 0 ? "text-up" : "text-down")}>
                {v === null ? "—" : formatPct(v, { decimals: 1 })}
              </TD>
            ))}
            <TD numeric className="font-semibold">{formatPct(r.year_total, { decimals: 1, signed: true })}</TD>
            <TD numeric className="text-ink-2">{formatPct(r.cdi_total, { decimals: 1 })}</TD>
            <TD numeric className="text-ink-2">
              {r.cdi_total ? formatPct((r.year_total / r.cdi_total) * 100, { decimals: 0 }) : "—"}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

export function RentabilidadeView() {
  const returns = useReturnSeries();
  const equity = useEquitySeries();
  const summary = useSummary();
  const [range, setRange] = React.useState<RangeKey>("12m");
  const today = summary.data?.as_of ?? new Date().toISOString().slice(0, 10);

  if (returns.isError) return <QueryError what="a rentabilidade" error={returns.error} onRetry={() => returns.refetch()} />;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented aria-label="Período" value={range} onChange={setRange} options={RANGE_OPTIONS} />
        <p className="text-sm text-ink-2">Rentabilidade pelo método de cotas, sem o efeito de aportes e resgates.</p>
      </div>
      <Panel>
        <PanelHeader title="Carteira contra Ibovespa e CDI" description="Retorno acumulado no período" />
        <div className="px-4 pb-4">
          {returns.data ? <ReturnsChart data={filterByRange(returns.data, range, today)} /> : <Skeleton className="h-[330px] w-full" />}
        </div>
      </Panel>
      <Panel>
        <PanelHeader title="Rentabilidade mensal" description="Retorno de cada mês e do ano, comparado ao CDI" />
        <div className="pb-2">{returns.data ? <MonthlyTable rows={monthlyReturns(returns.data)} /> : <Skeleton className="mx-4 mb-4 h-40" />}</div>
      </Panel>
      <Panel>
        <PanelHeader title="Evolução do patrimônio" />
        <div className="px-4 pb-4">
          {equity.data ? <EquityChart data={filterByRange(equity.data, range, today)} height={240} /> : <Skeleton className="h-[260px] w-full" />}
        </div>
      </Panel>
    </div>
  );
}
