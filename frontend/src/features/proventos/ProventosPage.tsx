import * as React from "react";
import { CalendarClock, Coins } from "lucide-react";
import { useAgendaEstimates, useDividends, useSummary } from "@/api/hooks";
import type { AssetClass, Dividend, DividendStatus } from "@/api/types";
import { AllocationBars } from "@/components/charts/AllocationStrip";
import { DividendBars } from "@/components/charts/DividendBars";
import { DividendStatusBadge } from "@/components/domain";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/form";
import { EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import {
  MONTH_LABELS,
  formatBRL,
  formatDate,
  formatDayMonth,
  formatMonthLong,
  formatNumber,
  formatQuantity,
} from "@/lib/format";
import { ASSET_CLASS_LABEL, ASSET_CLASS_SINGULAR, DIVIDEND_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { PageTitle, QueryError } from "../shared";
import { agenda, byAsset, isReceived, monthlyBars, monthOf, yearMonthTable } from "./aggregate";

type ClassFilter = AssetClass | "ALL";

function Summary({ dividends, today }: { dividends: Dividend[]; today: string }) {
  const yearAgo = `${Number(today.slice(0, 4)) - 1}${today.slice(4)}`;
  const received = dividends.filter(isReceived);
  const last12 = received.filter((d) => (d.pay_date ?? d.ex_date) > yearAgo).reduce((a, d) => a + Number(d.net), 0);
  const total = received.reduce((a, d) => a + Number(d.net), 0);
  const receivable = dividends.filter((d) => !isReceived(d)).reduce((a, d) => a + Number(d.net), 0);
  const taxes = received.filter((d) => (d.pay_date ?? d.ex_date) > yearAgo).reduce((a, d) => a + Number(d.tax), 0);
  const cells = [
    { label: "Média mensal", value: formatBRL(last12 / 12), sub: "últimos 12 meses" },
    { label: "Recebido em 12 meses", value: formatBRL(last12), sub: <>IR retido <span className="num">{formatBRL(taxes)}</span></> },
    { label: "Recebido desde o início", value: formatBRL(total) },
    { label: "A receber", value: formatBRL(receivable), sub: "já anunciados" },
  ];
  return (
    <dl className="mb-6 grid grid-cols-2 gap-y-4 border-y border-line py-4 md:grid-cols-4">
      {cells.map((c, i) => (
        <div key={c.label} className={cn("px-4", i % 2 === 0 && "pl-0 md:pl-4", i === 0 && "md:pl-0", i > 0 && "md:border-l md:border-line", i % 2 === 1 && "border-l border-line")}>
          <dt className="text-sm text-ink-2">{c.label}</dt>
          <dd className="num mt-1 text-xl font-semibold tracking-tight">{c.value}</dd>
          {c.sub && <dd className="mt-0.5 text-sm text-ink-2">{c.sub}</dd>}
        </div>
      ))}
    </dl>
  );
}

function Agenda({ dividends, today }: { dividends: Dividend[]; today: string }) {
  const estimates = useAgendaEstimates();
  const items = agenda(dividends, today, estimates.data ?? []);
  return (
    <Panel className="flex flex-col">
      <PanelHeader title="Agenda" description="Próximas datas-com e pagamentos" />
      {items.length === 0 ? (
        <EmptyState icon={CalendarClock} title="Nada agendado" className="py-8">
          Nenhum provento anunciado para os seus ativos.
        </EmptyState>
      ) : (
        <ol className="max-h-[22rem] overflow-y-auto px-4 pb-3">
          {items.map((i) => (
            <li key={`${i.kind}-${i.dividend.id}`} className="grid grid-cols-[3rem_1fr_auto] items-center gap-3 border-b border-line py-2.5 last:border-0">
              <span className="num leading-tight">
                <span className="block text-base font-semibold">{formatDayMonth(i.date).slice(0, 2)}</span>
                <span className="block text-xs uppercase text-muted">{MONTH_LABELS[Number(i.date.slice(5, 7)) - 1]}</span>
              </span>
              <span className="min-w-0">
                <span className="font-semibold">{i.dividend.ticker}</span>
                <span className="block text-sm text-ink-2">
                  {i.kind === "EX_DATE" ? "Data-com" : "Pagamento"} · {DIVIDEND_TYPE_LABEL[i.dividend.type]}
                  {i.kind === "PAYMENT" && !i.dividend.pay_date && " · data a definir"}
                </span>
              </span>
              <span className="text-right">
                <span className="num block font-medium">{formatBRL(i.dividend.net)}</span>
                <span className="num block text-sm text-muted">{formatBRL(i.dividend.amount_per_share, { precise: true })} por {i.dividend.asset_class === "STOCK" || i.dividend.asset_class === "BDR" ? "ação" : "cota"}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function HistoryTable({ dividends, today }: { dividends: Dividend[]; today: string }) {
  const rows = yearMonthTable(dividends, today);
  return (
    <Panel>
      <PanelHeader title="Histórico mensal" description="Proventos líquidos recebidos por mês" />
      <Table className="text-sm">
        <THead>
          <TR>
            <TH>Ano</TH>
            {MONTH_LABELS.map((m) => (
              <TH key={m} numeric className="capitalize">
                {m}
              </TH>
            ))}
            <TH numeric>Média</TH>
            <TH numeric>Total</TH>
          </TR>
        </THead>
        <TBody>
          {rows.map((r) => (
            <TR key={r.year}>
              <TD className="font-semibold">{r.year}</TD>
              {r.months.map((v, i) => (
                <TD key={i} numeric className={v === 0 ? "text-muted" : undefined}>
                  {formatNumber(v, { minDecimals: 2, maxDecimals: 2 })}
                </TD>
              ))}
              <TD numeric className="text-ink-2">{formatNumber(r.average, { minDecimals: 2, maxDecimals: 2 })}</TD>
              <TD numeric className="font-semibold">{formatBRL(r.total)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Panel>
  );
}

function DetailList({ dividends }: { dividends: Dividend[] }) {
  const years = [...new Set(dividends.map((d) => monthOf(d).slice(0, 4)))].sort().reverse();
  const [year, setYear] = React.useState(years[0] ?? "");
  const [status, setStatus] = React.useState<DividendStatus | "ALL">("ALL");
  const [limit, setLimit] = React.useState(25);
  const rows = dividends
    .filter((d) => monthOf(d).startsWith(year) && (status === "ALL" || d.status === status))
    .sort((a, b) => (b.pay_date ?? b.ex_date).localeCompare(a.pay_date ?? a.ex_date));
  const total = rows.reduce((a, d) => a + Number(d.net), 0);

  return (
    <Panel>
      <PanelHeader
        title="Meus proventos"
        description={
          <>
            {rows.length} lançamentos · líquido <span className="num font-medium text-ink">{formatBRL(total)}</span>
          </>
        }
        actions={
          <>
            <NativeSelect aria-label="Ano" value={year} onChange={(e) => setYear(e.target.value)} className="h-8 w-24 text-sm">
              {years.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as DividendStatus | "ALL")}
              className="h-8 w-44 text-sm"
            >
              <option value="ALL">Todos os status</option>
              <option value="ANNOUNCED">A receber</option>
              <option value="PAID">Pago</option>
              <option value="CONFIRMED">Conferido na B3</option>
            </NativeSelect>
          </>
        }
      />
      <Table>
        <THead>
          <TR className="bg-surface-2">
            <TH>Ativo</TH>
            <TH>Tipo</TH>
            <TH>Status</TH>
            <TH numeric>Data-com</TH>
            <TH numeric>Pagamento</TH>
            <TH numeric>Quant.</TH>
            <TH numeric>Valor por ação</TH>
            <TH numeric>Bruto</TH>
            <TH numeric>IR</TH>
            <TH numeric>Líquido</TH>
          </TR>
        </THead>
        <TBody>
          {rows.slice(0, limit).map((d) => (
            <TR key={d.id} className="hover:bg-surface-2">
              <TD>
                <span className="font-semibold">{d.ticker}</span>{" "}
                <span className="text-sm text-muted">{ASSET_CLASS_SINGULAR[d.asset_class]}</span>
              </TD>
              <TD>{DIVIDEND_TYPE_LABEL[d.type]}</TD>
              <TD>
                <DividendStatusBadge status={d.status} />
              </TD>
              <TD numeric>{formatDate(d.ex_date)}</TD>
              <TD numeric>{d.pay_date ? formatDate(d.pay_date) : <Badge tone="neutral">a definir</Badge>}</TD>
              <TD numeric>{formatQuantity(d.quantity)}</TD>
              <TD numeric>{formatBRL(d.amount_per_share, { precise: true })}</TD>
              <TD numeric>{formatBRL(d.gross)}</TD>
              <TD numeric className={Number(d.tax) ? undefined : "text-muted"}>{formatBRL(d.tax)}</TD>
              <TD numeric className="font-semibold">{formatBRL(d.net)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      {rows.length === 0 && (
        <EmptyState icon={Coins} title="Nenhum provento" className="py-8">
          Nada encontrado para os filtros escolhidos.
        </EmptyState>
      )}
      {rows.length > limit && (
        <div className="border-t border-line px-4 py-3 text-center">
          <Button variant="ghost" size="sm" onClick={() => setLimit((l) => l + 50)}>
            Mostrar mais ({rows.length - limit} restantes)
          </Button>
        </div>
      )}
    </Panel>
  );
}

export function ProventosPage() {
  const dividends = useDividends();
  const summary = useSummary();
  const today = summary.data?.as_of ?? new Date().toISOString().slice(0, 10);
  const [cls, setCls] = React.useState<ClassFilter>("ALL");
  const [selectedMonth, setSelectedMonth] = React.useState<string | null>(null);
  const [chartView, setChartView] = React.useState<"month" | "asset">("month");

  const all = dividends.data ?? [];
  const classes = (["STOCK", "FII", "ETF", "BDR"] as AssetClass[]).filter((c) => all.some((d) => d.asset_class === c));
  const scoped = cls === "ALL" ? all : all.filter((d) => d.asset_class === cls);
  const yearAgo = `${Number(today.slice(0, 4)) - 1}${today.slice(4)}`;
  const monthItems = selectedMonth ? scoped.filter((d) => monthOf(d) === selectedMonth) : [];

  return (
    <>
      <PageTitle title="Proventos" description="Dividendos, JCP e rendimentos: recebidos, conferidos e a receber." />
      {dividends.isError && <QueryError what="os proventos" error={dividends.error} onRetry={() => dividends.refetch()} />}
      {dividends.isPending ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : dividends.data ? (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Segmented
              aria-label="Classe de ativo"
              value={cls}
              onChange={setCls}
              options={[{ value: "ALL", label: "Todos" }, ...classes.map((c) => ({ value: c, label: ASSET_CLASS_LABEL[c] }))]}
            />
          </div>
          <Summary dividends={scoped} today={today} />
          <div className="grid gap-5 lg:grid-cols-3">
            <Panel className="lg:col-span-2">
              <PanelHeader
                title={chartView === "month" ? "Por mês" : "Por ativo"}
                description={
                  chartView === "asset"
                    ? "Recebidos nos últimos 12 meses"
                    : selectedMonth
                      ? `Detalhe de ${formatMonthLong(selectedMonth)}`
                      : "Clique em um mês para ver o detalhe"
                }
                actions={
                  <>
                    {chartView === "month" && selectedMonth && (
                      <Button size="sm" variant="ghost" onClick={() => setSelectedMonth(null)}>
                        Limpar seleção
                      </Button>
                    )}
                    <Segmented
                      aria-label="Agrupar proventos"
                      size="sm"
                      value={chartView}
                      onChange={setChartView}
                      options={[
                        { value: "month", label: "Por mês" },
                        { value: "asset", label: "Por ativo" },
                      ]}
                    />
                  </>
                }
              />
              <div className="px-4 pb-4">
                {chartView === "asset" ? (
                  <AllocationBars
                    className="pt-1"
                    slices={byAsset(scoped, yearAgo, today).map((a) => ({ key: a.ticker, label: a.ticker, value: a.total }))}
                  />
                ) : (
                  <>
                    <DividendBars
                      data={monthlyBars(scoped, today)}
                      selected={selectedMonth}
                      onSelectMonth={(m) => setSelectedMonth((cur) => (cur === m ? null : m))}
                    />
                    {selectedMonth && (
                      <ul className="mt-4 grid gap-x-6 border-t border-line pt-3 sm:grid-cols-2">
                        {monthItems.length === 0 && <li className="text-sm text-muted">Nenhum provento neste mês.</li>}
                        {monthItems.map((d) => (
                          <li key={d.id} className="flex items-center gap-2 py-1 text-sm">
                            <span className="w-16 font-semibold">{d.ticker}</span>
                            <span className="text-ink-2">{DIVIDEND_TYPE_LABEL[d.type]}</span>
                            <span className="num ml-auto font-medium">{formatBRL(d.net)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </div>
            </Panel>
            <Agenda dividends={scoped} today={today} />
          </div>
          <div className="mt-5">
            <HistoryTable dividends={scoped} today={today} />
          </div>
          <div className="mt-5">
            <DetailList key={cls} dividends={scoped} />
          </div>
        </>
      ) : null}
    </>
  );
}
