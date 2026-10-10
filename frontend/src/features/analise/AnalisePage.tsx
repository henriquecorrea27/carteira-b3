import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Ban, CheckCircle2, CircleDashed, CircleMinus, Search, TriangleAlert, XCircle } from "lucide-react";
import { useAnalysis, useAssetSearch, usePositions, usePriceBars } from "@/api/hooks";
import type { AssetAnalysis, Indicator, IndicatorStatus } from "@/api/types";
import { PriceChart } from "@/components/charts/PriceChart";
import { AssetMark, DecisionBadge, Delta, ScoreMeter } from "@/components/domain";
import { Badge } from "@/components/ui/badge";
import { Callout, EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatDate, formatMultiple, formatNumber, formatPct } from "@/lib/format";
import { ASSET_CLASS_SINGULAR } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { QueryError } from "../shared";

function TickerSearch({ autoFocus }: { autoFocus?: boolean }) {
  const navigate = useNavigate();
  const [q, setQ] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const search = useAssetSearch(q.trim(), open && q.trim().length > 0);
  const results = q.trim() ? (search.data ?? []) : [];

  const go = (ticker: string) => {
    navigate(`/analise/${ticker.toUpperCase()}`);
    setQ("");
    setOpen(false);
  };

  return (
    <div className="relative w-full max-w-xl">
      <Search className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" />
      <input
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls="analysis-search-results"
        aria-label="Pesquisar ação"
        autoFocus={autoFocus}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, results.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter") {
            const pick = results[active]?.ticker ?? q.trim();
            if (pick) go(pick);
          } else if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Pesquisar ação da B3, ex.: WEGE3 ou Itaú"
        className="h-12 w-full rounded-lg border border-line-strong bg-surface pl-11 pr-4 text-lg placeholder:text-muted focus-visible:border-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/10"
      />
      {open && results.length > 0 && (
        <ul id="analysis-search-results" role="listbox" className="absolute z-30 mt-1.5 w-full rounded-lg border border-line bg-surface p-1 shadow-[0_12px_32px_-12px_rgb(0_0_0/0.3)]">
          {results.map((r, i) => (
            <li
              key={r.ticker}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                go(r.ticker);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-default items-center gap-3 rounded-md px-2.5 py-2", i === active && "bg-sunken")}
            >
              <AssetMark ticker={r.ticker} assetClass={r.asset_class} className="size-7" />
              <span className="font-semibold">{r.ticker}</span>
              <span className="truncate text-ink-2">{r.name}</span>
              <span className="ml-auto text-sm text-muted">{ASSET_CLASS_SINGULAR[r.asset_class]}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const STATUS: Record<IndicatorStatus, { label: string; icon: typeof CheckCircle2; className: string }> = {
  GOOD: { label: "Bom", icon: CheckCircle2, className: "text-up" },
  MID: { label: "Médio", icon: TriangleAlert, className: "text-warn" },
  BAD: { label: "Ruim", icon: XCircle, className: "text-down" },
  NA: { label: "Sem dados", icon: CircleMinus, className: "text-muted" },
};

function formatIndicator(i: Indicator): string {
  if (i.value === null) return "—";
  switch (i.unit) {
    case "pct":
      return formatPct(i.value, { decimals: 1 });
    case "x":
      return formatMultiple(i.value);
    case "brl":
      return formatBRL(i.value);
    case "count":
      return formatNumber(i.value, { maxDecimals: 0 });
    default:
      return formatNumber(i.value, { minDecimals: 2, maxDecimals: 2 });
  }
}

function IndicatorTable({
  title,
  score,
  inconclusive,
  stale,
  rows,
}: {
  title: string;
  score: number | null;
  inconclusive: boolean;
  stale?: boolean;
  rows: Indicator[];
}) {
  const got = rows.reduce((a, r) => a + Number(r.points ?? 0), 0);
  const possible = rows.filter((r) => r.points !== null).reduce((a, r) => a + Number(r.max_points), 0);
  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-3">
            {title}
            <ScoreMeter score={score} inconclusive={inconclusive} size="lg" />
          </span>
        }
        description={
          inconclusive
            ? stale
              ? "Nota inconclusiva: os dados contábeis estão defasados. A decisão fica em Aguardar."
              : "Nota inconclusiva: mais de 30% do peso está sem dados. A decisão fica em Aguardar."
            : `${formatNumber(got, { maxDecimals: 1 })} de ${formatNumber(possible, { maxDecimals: 1 })} pontos possíveis`
        }
      />
      <Table>
        <THead>
          <TR className="bg-surface-2">
            <TH>Indicador</TH>
            <TH numeric>Valor</TH>
            <TH>Faixa ruim → ótimo</TH>
            <TH numeric>Pontos</TH>
            <TH>Status</TH>
          </TR>
        </THead>
        <TBody>
          {rows.map((r) => {
            const s = STATUS[r.status];
            const Icon = s.icon;
            const displayOnly = Number(r.max_points) === 0; // weight 0: shown, not scored
            const ratio = r.points === null || displayOnly ? 0 : Number(r.points) / Number(r.max_points);
            return (
              <TR key={r.key}>
                <TD className="font-medium">
                  {r.label}
                  {r.note && <div className="text-sm font-normal text-muted">{r.note}</div>}
                </TD>
                <TD numeric className="font-semibold">{formatIndicator(r)}</TD>
                <TD className="text-ink-2">{r.range_label}</TD>
                <TD numeric>
                  {displayOnly ? (
                    <span className="text-sm text-muted">só exibido</span>
                  ) : (
                    <span className="inline-flex items-center gap-2">
                      <span className="h-1 w-12 overflow-hidden rounded-full bg-sunken" aria-hidden>
                        <span className="block h-full rounded-full bg-ink-2" style={{ width: `${ratio * 100}%` }} />
                      </span>
                      <span className={r.points === null ? "text-muted" : undefined}>
                        {r.points === null ? "—" : formatNumber(r.points, { maxDecimals: 1 })}
                        <span className="text-muted">/{formatNumber(r.max_points, { maxDecimals: 1 })}</span>
                      </span>
                    </span>
                  )}
                </TD>
                <TD>
                  <span className={cn("inline-flex items-center gap-1.5 text-sm font-medium", s.className)}>
                    <Icon className="size-4" /> {s.label}
                  </span>
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
    </Panel>
  );
}

/** Current price placed between the Graham fair price and the Bazin ceiling on one scale. */
function PriceScale({ a }: { a: AssetAnalysis }) {
  const price = Number(a.price);
  const marks = [
    { key: "price", label: "Preço atual", value: price },
    ...(a.graham_fair_price ? [{ key: "graham", label: "Preço justo Graham", value: Number(a.graham_fair_price) }] : []),
    ...(a.bazin_ceiling ? [{ key: "bazin", label: "Preço teto Bazin", value: Number(a.bazin_ceiling) }] : []),
  ];
  const min = Math.min(...marks.map((m) => m.value)) * 0.85;
  const max = Math.max(...marks.map((m) => m.value)) * 1.08;
  const pos = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div>
      <div className="relative mx-1 mb-1 mt-9 h-1.5 rounded-full bg-sunken">
        {marks.map((m) => (
          <div key={m.key} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${pos(m.value)}%` }}>
            <span
              className={cn(
                "block rounded-full ring-2 ring-surface",
                m.key === "price" ? "size-3.5 bg-ink" : "size-2.5 bg-ink-2",
              )}
            />
            {m.key === "price" && (
              <span className="num absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-sm bg-ink px-1.5 py-0.5 text-xs font-semibold text-paper">
                {formatBRL(m.value)}
              </span>
            )}
          </div>
        ))}
      </div>
      <dl className="mt-5 flex flex-col gap-2.5">
        {marks.map((m) => (
          <div key={m.key} className="flex items-baseline justify-between gap-3">
            <dt className="flex items-center gap-2 text-ink-2">
              <span aria-hidden className={cn("rounded-full", m.key === "price" ? "size-2.5 bg-ink" : "size-2 bg-ink-2")} />
              {m.label}
            </dt>
            <dd className="num font-semibold">
              {formatBRL(m.value)}
              {m.key !== "price" && (
                <span className={cn("ml-2 text-sm font-normal", m.value >= price ? "text-up" : "text-down")}>
                  {formatPct(((m.value - price) / price) * 100, { decimals: 0, signed: true })}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Eliminatory({ a }: { a: AssetAnalysis }) {
  return (
    <Panel>
      <PanelHeader title="Eliminatórios" description="Falhar em qualquer um leva a Evitar" />
      <ul className="px-4 pb-3">
        {a.eliminatory.map((e) => {
          const Icon = e.passed === null ? CircleDashed : e.passed ? CheckCircle2 : Ban;
          return (
            <li key={e.id} className="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
              <Icon className={cn("size-4 shrink-0", e.passed === null ? "text-muted" : e.passed ? "text-up" : "text-down")} />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{e.label}</span>
                <span className="block text-sm text-ink-2">
                  {e.id} · {e.rule}
                </span>
              </span>
              <span className="max-w-[45%] text-right">
                <span className="num block font-semibold">{e.value_label ?? "—"}</span>
                <span className={cn("block text-sm", e.passed === null ? "text-muted" : e.passed ? "text-up" : "text-down")}>
                  {e.passed === null ? "Sem dados" : e.passed ? "Passou" : "Falhou"}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function PricePanel({ ticker }: { ticker: string }) {
  const bars = usePriceBars(ticker);
  const [mode, setMode] = React.useState<"area" | "candles">("area");
  const [range, setRange] = React.useState<"6m" | "1y" | "2y">("1y");
  const data = React.useMemo(() => {
    if (!bars.data) return [];
    const days = range === "6m" ? 126 : range === "1y" ? 252 : bars.data.length;
    return bars.data.slice(-days);
  }, [bars.data, range]);
  return (
    <Panel>
      <PanelHeader
        title="Cotação"
        actions={
          <>
            <Segmented aria-label="Período do gráfico" size="sm" value={range} onChange={setRange} options={[{ value: "6m", label: "6M" }, { value: "1y", label: "1A" }, { value: "2y", label: "2A" }]} />
            <Segmented aria-label="Tipo de gráfico" size="sm" value={mode} onChange={setMode} options={[{ value: "area", label: "Linha" }, { value: "candles", label: "Candles" }]} />
          </>
        }
      />
      <div className="px-2 pb-3">{bars.data ? <PriceChart bars={data} mode={mode} /> : <Skeleton className="mx-2 h-80" />}</div>
    </Panel>
  );
}

function AnalysisView({ ticker }: { ticker: string }) {
  const analysis = useAnalysis(ticker);
  const positions = usePositions();
  const held = positions.data?.find((p) => p.ticker === ticker);

  if (analysis.isPending)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  if (analysis.isError)
    return analysis.error.message.startsWith("Não encontramos") ? (
      <Panel>
        <EmptyState icon={Search} title={analysis.error.message}>
          Confira o código de negociação. Ações terminam em 3, 4, 5, 6 ou 11 (units).
        </EmptyState>
      </Panel>
    ) : (
      <QueryError what={`a análise de ${ticker}`} error={analysis.error} onRetry={() => analysis.refetch()} />
    );

  const a = analysis.data;
  const quality = a.indicators.filter((i) => i.group === "QUALITY");
  const price = a.indicators.filter((i) => i.group === "PRICE");
  const isStock = a.asset_class === "STOCK";

  return (
    <div className="flex flex-col gap-5">
      <section className="grid gap-6 border-b border-line pb-6 lg:grid-cols-[1fr_auto]">
        <div className="flex items-start gap-4">
          <AssetMark ticker={a.ticker} assetClass={a.asset_class} className="size-12 text-xs" />
          <div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="text-xl font-semibold tracking-tight">{a.ticker}</h1>
              <span className="text-ink-2">{a.name}</span>
              {a.sector && <Badge tone="outline">{a.sector}</Badge>}
              {held && <Badge tone="neutral">Na carteira · {formatNumber(held.quantity)} ações</Badge>}
            </div>
            <div className="mt-2 flex flex-wrap items-baseline gap-x-3">
              <span className="text-[2.25rem] font-semibold leading-none tracking-tight">{formatBRL(a.price)}</span>
              <Delta value={a.day_change_pct} />
              <span className="text-sm text-muted">fechamento de {formatDate(a.price_date)}</span>
            </div>
          </div>
        </div>
        {isStock && (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 lg:justify-end">
            <div>
              <p className="mb-1.5 text-sm text-ink-2">Decisão</p>
              <DecisionBadge decision={a.decision} className="px-2.5 py-1 text-base" />
            </div>
            <div>
              <p className="text-sm text-ink-2">Nota final</p>
              <p className="num text-[2.25rem] font-semibold leading-none tracking-tight">{a.score_final ?? "—"}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="flex items-center justify-between gap-4 text-sm text-ink-2">
                Qualidade <ScoreMeter score={a.score_quality} inconclusive={a.quality_inconclusive} />
              </span>
              <span className="flex items-center justify-between gap-4 text-sm text-ink-2">
                Preço <ScoreMeter score={a.score_price} inconclusive={a.price_inconclusive} />
              </span>
            </div>
          </div>
        )}
      </section>

      {a.warnings.length > 0 && (
        <Callout tone="warn" title="Atenção nesta análise">
          <ul className="list-disc pl-4">
            {a.warnings.map((w) => (
              <li key={w.message}>{w.message}</li>
            ))}
          </ul>
        </Callout>
      )}
      {a.special_sector === "FINANCIAL" && (
        <Callout tone="info" title="Análise parcial — setor financeiro">
          Bancos e seguradoras não usam EBITDA, dívida líquida, ROIC, EV/EBIT, liquidez corrente nem fluxo de caixa. A qualidade pesa ROE, crescimento do lucro e do patrimônio, PL / ativo (só bancos) e payout; o preço, P/L, DY e P/VP.
        </Callout>
      )}
      {a.special_sector === "UTILITY" && (
        <Callout tone="info" title="Setor de utilidade pública">
          Pesos e faixas próprios (dívida mais alta é normal e o dividendo pesa mais). O eliminatório de dívida líquida / EBITDA vai até 4,5 em vez de 3,5.
        </Callout>
      )}
      {a.special_sector === "CYCLICAL" && (
        <Callout tone="info" title="Setor cíclico (commodities)">
          P/L e EV/EBIT usam o lucro e o EBIT médios de 5 anos, e a dívida é medida contra o EBITDA médio de 5 anos (limite 3,0): um ano de pico ou de vale engana. O crescimento do lucro não entra na nota.
        </Callout>
      )}
      {!isStock && (
        <Callout tone="info" title={`${ASSET_CLASS_SINGULAR[a.asset_class]}s ainda não têm regras de análise`}>
          Por enquanto só ações recebem nota e decisão. O gráfico de cotação continua disponível.
        </Callout>
      )}

      {isStock ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-5">
            <IndicatorTable title="Qualidade" score={a.score_quality} inconclusive={a.quality_inconclusive} stale={a.stale} rows={quality} />
            <IndicatorTable title="Preço" score={a.score_price} inconclusive={a.price_inconclusive} stale={a.stale} rows={price} />
          </div>
          <div className="flex flex-col gap-5">
            <Eliminatory a={a} />
            <Panel>
              <PanelHeader title="Preço justo e preço teto" />
              <div className="px-4 pb-4">
                <PriceScale a={a} />
                <p className="mt-4 text-sm text-ink-2">
                  Graham: √(22,5 × LPA × VPA). Bazin: proventos médios de 5 anos ÷ 6%. DY médio 5 anos{" "}
                  <span className="num font-medium text-ink">{formatPct(a.dy_5y_pct, { decimals: 1 })}</span>.
                </p>
              </div>
            </Panel>
          </div>
        </div>
      ) : null}

      <PricePanel ticker={a.ticker} />

      <p className="text-sm text-muted">
        Dados contábeis: {a.fundamentals_ref ?? "—"}
        {a.fundamentals_date && ` (data-base ${formatDate(a.fundamentals_date)})`} · Cotação de {formatDate(a.price_date)} · Regras v2 (pesos por setor, revisão em 30/04/2027).
      </p>
    </div>
  );
}

export function AnalisePage() {
  const { ticker } = useParams();
  const positions = usePositions();
  const stocks = (positions.data ?? []).filter((p) => p.rules);

  return (
    <>
      <div className={cn("flex flex-col gap-4", ticker ? "mb-6" : "mb-8 items-start pt-6")}>
        {!ticker && (
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Análise</h1>
            <p className="mt-1 text-ink-2">Indicadores e decisão por regras para qualquer ação, sempre com o porquê.</p>
          </div>
        )}
        <TickerSearch key={ticker ?? "home"} autoFocus={!ticker} />
      </div>
      {ticker ? (
        <AnalysisView ticker={ticker.toUpperCase()} />
      ) : (
        stocks.length > 0 && (
          <section aria-label="Ações da carteira">
            <h2 className="mb-3 text-lg font-semibold">Suas ações</h2>
            <ul className="grid overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-2 lg:grid-cols-3">
              {stocks.map((p) => (
                <li key={p.ticker} className="-mb-px -mr-px border-b border-r border-line">
                  <Link to={`/analise/${p.ticker}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
                    <AssetMark ticker={p.ticker} assetClass={p.asset_class} />
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">{p.ticker}</span>
                      <span className="block truncate text-sm text-ink-2">{p.rules!.main_reason}</span>
                    </span>
                    <span className="flex flex-col items-end gap-1">
                      <DecisionBadge decision={p.rules!.decision} />
                      <ScoreMeter score={p.rules!.score_final} inconclusive={p.rules!.inconclusive} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )
      )}
    </>
  );
}
