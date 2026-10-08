import * as React from "react";
import { Link } from "react-router-dom";
import { CalendarClock } from "lucide-react";
import { useAgendaEstimates, useDividends, useEquitySeries, usePositions, useSummary } from "@/api/hooks";
import type { Decision, Position } from "@/api/types";
import { AllocationStrip } from "@/components/charts/AllocationStrip";
import { DividendBars } from "@/components/charts/DividendBars";
import { EquityChart } from "@/components/charts/EquityChart";
import { DecisionBadge, Delta, ScoreMeter } from "@/components/domain";
import { Button } from "@/components/ui/button";
import { EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { formatBRL, formatDayMonth, formatPct } from "@/lib/format";
import { DECISION_LABEL, DIVIDEND_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { agenda, monthlyBars } from "../proventos/aggregate";
import { RANGE_OPTIONS, filterByRange, type RangeKey } from "../shared";

function StatStrip() {
  const { data, isPending } = useSummary();
  const cells: { label: string; value: React.ReactNode; sub?: React.ReactNode }[] = data
    ? [
        { label: "Valor investido", value: formatBRL(data.invested) },
        {
          label: "Lucro em aberto",
          value: <Delta value={data.unrealized_pnl} kind="brl" arrow={false} className="font-semibold" />,
          sub: <>Realizado <span className="num">{formatBRL(data.realized_pnl, { signed: true })}</span></>,
        },
        {
          label: "Rentabilidade 12 meses",
          value: <Delta value={data.return_12m_pct} arrow={false} className="font-semibold" />,
          sub: <>Total <span className="num">{formatPct(data.total_return_pct, { signed: true })}</span></>,
        },
        {
          label: "Proventos 12 meses",
          value: formatBRL(data.dividends_12m),
          sub: <>Total <span className="num">{formatBRL(data.dividends_total)}</span></>,
        },
        { label: "A receber", value: formatBRL(data.dividends_receivable), sub: "proventos anunciados" },
      ]
    : [];
  return (
    <dl className="mb-8 grid grid-cols-2 border-y border-line md:grid-cols-5">
      {isPending
        ? Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="px-4 py-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-2 h-6 w-32" />
            </div>
          ))
        : cells.map((c, i) => (
            <div
              key={c.label}
              className={cn(
                "px-4 py-4 first:pl-0",
                i > 0 && "md:border-l md:border-line",
                i % 2 === 1 && "border-l border-line md:border-l",
                i >= 2 && "border-t border-line md:border-t-0",
                i % 2 === 0 && "pl-0 md:pl-4",
              )}
            >
              <dt className="text-sm text-ink-2">{c.label}</dt>
              <dd className="num mt-1 text-xl font-semibold tracking-tight">{c.value}</dd>
              {c.sub && <dd className="mt-0.5 text-sm text-ink-2">{c.sub}</dd>}
            </div>
          ))}
    </dl>
  );
}

const DECISION_ORDER: Decision[] = ["BUY", "WAIT", "AVOID"];

function RulesDigest({ positions }: { positions: Position[] }) {
  const stocks = positions.filter((p) => p.rules);
  return (
    <Panel className="flex flex-col">
      <PanelHeader title="O que as regras dizem" description="Ações da carteira pela decisão de hoje" />
      <div className="flex flex-1 flex-col gap-4 px-4 pb-4">
        {DECISION_ORDER.map((d) => {
          const group = stocks.filter((p) => p.rules!.decision === d).sort((a, b) => b.rules!.score_final - a.rules!.score_final);
          return (
            <div key={d}>
              <div className="mb-1.5 flex items-center justify-between">
                <DecisionBadge decision={d} />
                <span className="text-sm text-muted">{group.length === 1 ? "1 ação" : `${group.length} ações`}</span>
              </div>
              {group.length === 0 ? (
                <p className="text-sm text-muted">Nenhuma ação para {DECISION_LABEL[d].toLowerCase()}.</p>
              ) : (
                <ul className="flex flex-col">
                  {group.map((p) => (
                    <li key={p.ticker}>
                      <Link
                        to={`/analise/${p.ticker}`}
                        className="-mx-2 flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-surface-2"
                      >
                        <span className="w-16 font-semibold">{p.ticker}</span>
                        <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{p.rules!.main_reason}</span>
                        <ScoreMeter score={p.rules!.score_final} inconclusive={p.rules!.inconclusive} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function UpcomingDividends() {
  const { data, isPending } = useDividends();
  const summary = useSummary();
  const today = summary.data?.as_of ?? new Date().toISOString().slice(0, 10);
  const estimates = useAgendaEstimates();
  const items = data ? agenda(data, today, estimates.data ?? []).slice(0, 6) : [];
  return (
    <Panel className="flex flex-col">
      <PanelHeader
        title="Agenda"
        description="Próximas datas-com e pagamentos"
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link to="/proventos">Ver proventos</Link>
          </Button>
        }
      />
      {isPending ? (
        <div className="flex flex-col gap-2 px-4 pb-4">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={CalendarClock} title="Nada agendado" className="py-8">
          Quando uma empresa anunciar proventos dos seus ativos, as datas aparecem aqui.
        </EmptyState>
      ) : (
        <ul className="flex-1 px-4 pb-3">
          {items.map((i) => (
            <li key={`${i.kind}-${i.dividend.id}`} className="flex items-center gap-3 border-b border-line py-2 last:border-0">
              <span className="num w-12 text-sm font-semibold">{formatDayMonth(i.date)}</span>
              <span className="min-w-0 flex-1">
                <span className="font-semibold">{i.dividend.ticker}</span>{" "}
                <span className="text-sm text-ink-2">
                  {i.kind === "EX_DATE" ? "data-com" : "pagamento"} · {DIVIDEND_TYPE_LABEL[i.dividend.type]}
                </span>
              </span>
              <span className="num text-sm">{formatBRL(i.dividend.net)}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function ResumoView() {
  const positions = usePositions();
  const equity = useEquitySeries();
  const dividends = useDividends();
  const summary = useSummary();
  const [range, setRange] = React.useState<RangeKey>("24m");
  const today = summary.data?.as_of ?? new Date().toISOString().slice(0, 10);

  return (
    <>
      <section aria-label="Distribuição por ativo" className="mb-8">
        {positions.data ? (
          <AllocationStrip slices={positions.data.map((p) => ({ key: p.ticker, label: p.ticker, value: Number(p.market_value) }))} />
        ) : (
          <Skeleton className="h-3 w-full" />
        )}
      </section>

      <StatStrip />

      <div className="grid gap-5 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Evolução do patrimônio"
            description="Quanto a carteira vale contra quanto você aplicou"
            actions={<Segmented aria-label="Período" size="sm" value={range} onChange={setRange} options={RANGE_OPTIONS} />}
          />
          <div className={cn("px-4 pb-4 transition-opacity", equity.isFetching && "opacity-60")}>
            {equity.data ? <EquityChart data={filterByRange(equity.data, range, today)} /> : <Skeleton className="h-[300px] w-full" />}
          </div>
        </Panel>
        {positions.data ? <RulesDigest positions={positions.data} /> : <Skeleton className="h-full min-h-80" />}

        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Proventos por mês"
            description="Valores líquidos dos últimos 12 meses e o que já foi anunciado"
          />
          <div className="px-4 pb-4">
            {dividends.data ? <DividendBars data={monthlyBars(dividends.data, today)} height={220} /> : <Skeleton className="h-[240px] w-full" />}
          </div>
        </Panel>
        <UpcomingDividends />
      </div>
    </>
  );
}
