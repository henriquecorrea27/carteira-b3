import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Ban, CheckCircle2, CircleDashed, Ruler, Search } from "lucide-react";
import { useAnalysis, useAssetSearch, usePositions, usePriceBars } from "@/api/hooks";
import type { AssetAnalysis, Indicator } from "@/api/types";
import { Legend } from "@/components/charts/common";
import { PriceChart } from "@/components/charts/PriceChart";
import { AssetMark, DecisionBadge, Delta, ScoreMeter } from "@/components/domain";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InfoTip } from "@/components/ui/menu";
import { Callout, EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatDate, formatMultiple, formatNumber, formatPct, toNumber, type Numeric } from "@/lib/format";
import { ASSET_CLASS_SINGULAR } from "@/lib/labels";
import { sma } from "@/lib/indicators";
import { cn } from "@/lib/utils";
import { QueryError } from "../shared";
import { ELIMINATORY_TERMS, INDICATOR_TERMS, TERMS, type Term } from "./glossary";
import { HistorySection } from "./HistorySection";
import { IndicatorPanel } from "./IndicatorPanel";
import { STATUS, Tip, formatBig, formatBigBRL } from "./shared";

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
  term,
}: {
  title: string;
  term?: Term;
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
            <span className="flex items-center gap-1.5">
              {title}
              {term && <Tip term={term} />}
            </span>
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
            <TH>
              <span className="inline-flex items-center gap-1">
                Faixa ruim → ótimo <Tip term={TERMS.range} />
              </span>
            </TH>
            <TH numeric>
              <span className="inline-flex items-center gap-1">
                Pontos <Tip term={TERMS.points} />
              </span>
            </TH>
            <TH>
              <span className="inline-flex items-center gap-1">
                Status <Tip term={TERMS.status} />
              </span>
            </TH>
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
                  <span className="inline-flex items-center gap-1.5">
                    {r.label}
                    {INDICATOR_TERMS[r.key] && <Tip term={INDICATOR_TERMS[r.key]} side="right" />}
                  </span>
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
    { key: "price", label: "Preço atual", value: price, term: null as Term | null },
    ...(a.graham_fair_price ? [{ key: "graham", label: "Preço justo Graham", value: Number(a.graham_fair_price), term: TERMS.graham }] : []),
    ...(a.bazin_ceiling ? [{ key: "bazin", label: "Preço teto Bazin", value: Number(a.bazin_ceiling), term: TERMS.bazin }] : []),
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
              {m.term && <Tip term={m.term} />}
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

function CalcRow({ label, term, value, detail }: { label: string; term?: Term; value: string; detail?: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <dt className="flex items-center gap-1 text-ink-2">
          {label}
          {term && <Tip term={term} />}
        </dt>
        <dd className="num font-medium">{value}</dd>
      </div>
      {detail && <p className="num text-xs text-muted">{detail}</p>}
    </div>
  );
}

function Result({ children }: { children: React.ReactNode }) {
  return <p className="num mt-2.5 rounded-md bg-surface-2 px-3 py-2 text-sm">{children}</p>;
}

/** Step-by-step Graham fair price and Bazin ceiling, from the same inputs the backend used. */
function ValuationCalc({ a }: { a: AssetAnalysis }) {
  const v = a.valuation;
  if (!v) return null;
  // Up to 4 decimals so the formula checks by hand against the result (computed with full precision)
  const exact = (n: Numeric) => formatNumber(n, { minDecimals: 2, maxDecimals: 4 });
  const years = v.dps_by_year;
  return (
    <div className="mt-5 flex flex-col gap-5 border-t border-line pt-4 text-sm">
      <section aria-label="Cálculo do preço justo de Graham">
        <h3 className="mb-2 flex items-center gap-1.5 font-semibold">
          Cálculo de Graham <Tip term={TERMS.graham} />
        </h3>
        <dl className="flex flex-col gap-2">
          <CalcRow
            label="LPA (12 meses)"
            term={TERMS.eps}
            value={formatBRL(v.eps)}
            detail={v.net_income_ttm !== null && v.shares !== null ? `lucro ${formatBigBRL(v.net_income_ttm)} ÷ ${formatBig(v.shares)} ações` : undefined}
          />
          <CalcRow
            label="VPA"
            term={TERMS.bvps}
            value={formatBRL(v.bvps)}
            detail={v.equity !== null && v.shares !== null ? `patrimônio ${formatBigBRL(v.equity)} ÷ ${formatBig(v.shares)} ações` : undefined}
          />
        </dl>
        {a.graham_fair_price ? (
          <Result>
            √(22,5 × {exact(v.eps)} × {exact(v.bvps)}) = <strong className="font-semibold">{formatBRL(a.graham_fair_price)}</strong>
          </Result>
        ) : (
          <p className="mt-2.5 text-muted">Não se aplica: {v.graham_note ?? "LPA ou VPA indisponível"}.</p>
        )}
      </section>

      <section aria-label="Cálculo do preço teto de Bazin">
        <h3 className="mb-2 flex items-center gap-1.5 font-semibold">
          Cálculo de Bazin <Tip term={TERMS.bazin} />
        </h3>
        {years.length > 0 ? (
          <>
            <p className="mb-1.5 flex items-center gap-1 text-ink-2">
              Proventos por ação pagos no ano <Tip term={TERMS.dps} />
            </p>
            <dl className="flex flex-col gap-1">
              {years.map((y) => (
                <div key={y.year} className="flex justify-between gap-4">
                  <dt className="num text-ink-2">{y.year}</dt>
                  <dd className="num">{formatBRL(y.dps, { precise: true })}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-4 border-t border-line pt-1 font-medium">
                <dt>
                  Média de {years.length} {years.length === 1 ? "ano" : "anos"}
                </dt>
                <dd className="num">{formatBRL(v.dps_5y, { precise: true })}</dd>
              </div>
            </dl>
            {a.bazin_ceiling ? (
              <Result>
                {exact(v.dps_5y)} ÷ 6% = <strong className="font-semibold">{formatBRL(a.bazin_ceiling)}</strong>
                <span className="mt-1 block text-ink-2">
                  DY médio: {exact(v.dps_5y)} ÷ {exact(a.price)} = {formatPct(a.dy_5y_pct, { decimals: 1 })}
                </span>
              </Result>
            ) : (
              <p className="mt-2.5 text-muted">Não calculado: {v.dps_note ?? "proventos indisponíveis"}.</p>
            )}
          </>
        ) : (
          <p className="text-muted">Sem proventos pagos nos balanços da CVM: não há preço teto.</p>
        )}
      </section>
    </div>
  );
}

function Eliminatory({ a }: { a: AssetAnalysis }) {
  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-1.5">
            Eliminatórios <Tip term={TERMS.eliminatory} />
          </span>
        }
        description="Falhar em qualquer um leva a Evitar"
      />
      <ul className="px-4 pb-3">
        {a.eliminatory.map((e) => {
          const Icon = e.passed === null ? CircleDashed : e.passed ? CheckCircle2 : Ban;
          return (
            <li key={e.id} className="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
              <Icon className={cn("size-4 shrink-0", e.passed === null ? "text-muted" : e.passed ? "text-up" : "text-down")} />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{e.label}</span>
                {ELIMINATORY_TERMS[e.id] && (
                  <InfoTip title={e.label} side="left" className="ml-1.5">
                    {ELIMINATORY_TERMS[e.id]}
                  </InfoTip>
                )}
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

const SMA_DAYS = 200;

/** Where the price sits between the cheap and the expensive distance from the SMA, and how it scores. */
function TechnicalPanel({ a }: { a: AssetAnalysis }) {
  const t = a.technical;
  if (!t) return null;
  const cheap = Number(t.cheap_pct);
  const expensive = Number(t.expensive_pct);
  const d = toNumber(t.distance_pct);
  const perPct = 100 / (expensive - cheap); // points lost per 1% above the cheap end
  const clamped = d === null ? null : Math.min(Math.max(d, cheap), expensive);
  const pos = clamped === null ? 0 : ((clamped - cheap) / (expensive - cheap)) * 100;
  const fundamental = a.score_price_fundamental;
  const blended = fundamental !== null && t.score !== null ? (1 - a.technical_weight) * fundamental + a.technical_weight * t.score : null;
  // Only the loss cap lowers the price below the blend (0,1 tolerance: the backend rounds the blend)
  const capped = blended !== null && a.score_price !== null && a.score_price < blended - 0.15;
  const pct = (n: number) => formatNumber(n * 100, { maxDecimals: 0 });
  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-3">
            <span className="flex items-center gap-1.5">
              Análise gráfica — MM{t.sma_days} <Tip term={TERMS.technical} />
            </span>
            <ScoreMeter score={t.score} inconclusive={false} size="lg" />
          </span>
        }
        description={`Preço comparado com a média dos últimos ${t.sma_days} pregões (gráfico diário). Peso de ${pct(a.technical_weight || 0.25)}% na nota de Preço.`}
      />
      <div className="px-4 pb-4">
        <dl className="grid grid-cols-3 gap-4">
          <div>
            <dt className="text-sm text-ink-2">Preço atual</dt>
            <dd className="num text-lg font-semibold">{formatBRL(t.price)}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1 text-sm text-ink-2">
              MM{t.sma_days} <Tip term={TERMS.sma} />
            </dt>
            <dd className="num text-lg font-semibold">{formatBRL(t.sma)}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1 text-sm text-ink-2">
              Distância <Tip term={TERMS.distance} />
            </dt>
            <dd className={cn("num text-lg font-semibold", d === null ? "text-muted" : d > 0 ? "text-down" : d < 0 ? "text-up" : undefined)}>
              {d === null ? "—" : formatPct(d, { decimals: 1, signed: true })}
            </dd>
          </div>
        </dl>

        {t.score === null ? (
          <p className="mt-4 text-sm text-muted">
            Sem nota gráfica: {t.note ?? "histórico insuficiente"}. A nota de Preço usa só os fundamentos.
          </p>
        ) : (
          <>
            <div className="mt-6" aria-hidden>
              <div className="relative h-2 rounded-full bg-gradient-to-r from-up via-warn to-down opacity-70">
                <span className="absolute top-1/2 left-1/2 h-4 w-px -translate-y-1/2 bg-ink-2" />
                <span
                  className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink ring-2 ring-surface"
                  style={{ left: `${pos}%` }}
                />
              </div>
              <div className="num mt-2 grid grid-cols-3 text-xs text-ink-2">
                <span>
                  {formatPct(cheap, { decimals: 0 })} ou menos
                  <span className="block font-medium text-up">barato · 100</span>
                </span>
                <span className="text-center">
                  na MM{t.sma_days}
                  <span className="block font-medium">de olho · 50</span>
                </span>
                <span className="text-right">
                  {formatPct(expensive, { decimals: 0, signed: true })} ou mais
                  <span className="block font-medium text-down">caro · 0</span>
                </span>
              </div>
            </div>
            <div className="num mt-4 flex flex-col gap-1 rounded-md bg-surface-2 px-3 py-2 text-sm">
              <span>
                Nota gráfica:{" "}
                {d !== null && d > cheap && d < expensive ? (
                  <>
                    50 − {formatNumber(perPct, { maxDecimals: 2 })} × ({formatNumber(d, { minDecimals: 2, maxDecimals: 2 })}) ={" "}
                  </>
                ) : (
                  <>além do limite de {formatPct(d !== null && d < 0 ? cheap : expensive, { decimals: 0, signed: true })} → </>
                )}
                <strong className="font-semibold">{formatNumber(t.score, { maxDecimals: 1 })}</strong>
              </span>
              {blended !== null && (
                <span className="text-ink-2">
                  Nota de Preço: {formatNumber(1 - a.technical_weight, { maxDecimals: 2 })} × {formatNumber(fundamental, { maxDecimals: 1 })} (fundamentos) +{" "}
                  {formatNumber(a.technical_weight, { maxDecimals: 2 })} × {formatNumber(t.score, { maxDecimals: 1 })} (gráfica) ={" "}
                  <strong className="font-semibold text-ink">{formatNumber(capped ? blended : a.score_price, { minDecimals: 1, maxDecimals: 1 })}</strong>
                  {capped && <> → limitada a {formatNumber(a.score_price, { maxDecimals: 1 })} (prejuízo nos últimos 12 meses)</>}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

function PricePanel({ ticker }: { ticker: string }) {
  const bars = usePriceBars(ticker);
  const [mode, setMode] = React.useState<"area" | "candles">("candles");
  const [range, setRange] = React.useState<"6m" | "1y" | "2y" | "5y">("1y");
  const [ruler, setRuler] = React.useState(false);
  const smaLine = React.useMemo(() => {
    if (!bars.data) return [];
    // The first 199 days have no SMA
    const values = sma(bars.data.map((b) => Number(b.close)), SMA_DAYS);
    return bars.data.flatMap((b, i) => (values[i] === null ? [] : [{ time: b.time, value: values[i]! }]));
  }, [bars.data]);
  const visibleBars = { "6m": 126, "1y": 252, "2y": 504, "5y": null }[range];
  return (
    <Panel id="cotacao" className="scroll-mt-20">
      <PanelHeader
        title="Cotação"
        description="Gráfico diário ajustado por desdobramentos e bonificações. Arraste para mover, use a roda do mouse para dar zoom; a régua (ou Shift + clique) mede a variação entre dois pontos."
        actions={
          <>
            <Segmented aria-label="Período do gráfico" size="sm" value={range} onChange={setRange} options={[{ value: "6m", label: "6M" }, { value: "1y", label: "1A" }, { value: "2y", label: "2A" }, { value: "5y", label: "5A" }]} />
            <Segmented aria-label="Tipo de gráfico" size="sm" value={mode} onChange={setMode} options={[{ value: "candles", label: "Candles" }, { value: "area", label: "Linha" }]} />
            <Button
              size="sm"
              variant={ruler ? "primary" : "secondary"}
              aria-pressed={ruler}
              onClick={() => setRuler((r) => !r)}
              title="Medir a variação entre dois pontos (atalho: Shift + clique no gráfico)"
            >
              <Ruler aria-hidden /> Régua
            </Button>
          </>
        }
      />
      <div className="px-2 pb-3">
        {bars.data ? (
          <PriceChart
            bars={bars.data}
            mode={mode}
            overlay={smaLine}
            overlayLabel={`MM${SMA_DAYS}`}
            visibleBars={visibleBars}
            ruler={ruler}
            onRulerChange={setRuler}
          />
        ) : (
          <Skeleton className="mx-2 h-[420px]" />
        )}
        {smaLine.length > 0 && (
          <Legend
            className="px-2 pt-2"
            items={[
              ...(mode === "area" ? [{ label: "Fechamento diário", color: "var(--series-1)" }] : []),
              { label: `MM${SMA_DAYS} (média de ${SMA_DAYS} pregões)`, color: "var(--series-2)" },
            ]}
          />
        )}
      </div>
    </Panel>
  );
}

const SECTIONS = [
  { id: "regras", label: "Análise por regras" },
  { id: "indicadores", label: "Indicadores" },
  { id: "cotacao", label: "Cotação" },
  { id: "resultados", label: "Resultados", history: true },
  { id: "dividendos", label: "Dividendos", history: true },
  { id: "historico", label: "Histórico", history: true },
];

function SectionTitle({ id, title, term, children }: { id?: string; title: string; term: Term; children: React.ReactNode }) {
  return (
    <header id={id} className="scroll-mt-20 border-t border-line pt-6">
      <h2 className="flex items-center gap-1.5 text-xl font-semibold tracking-tight">
        {title} <Tip term={term} />
      </h2>
      <p className="mt-1 max-w-3xl text-ink-2">{children}</p>
    </header>
  );
}

/** In-page shortcuts to the sections of a long analysis. */
function SectionNav({ hasHistory }: { hasHistory: boolean }) {
  return (
    <nav aria-label="Seções da análise" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
      {SECTIONS.filter((s) => hasHistory || !s.history).map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          onClick={(e) => {
            e.preventDefault();
            document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          className="shrink-0 rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink-2 hover:border-line-strong hover:text-ink"
        >
          {s.label}
        </a>
      ))}
    </nav>
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
              <p className="mb-1.5 flex items-center gap-1 text-sm text-ink-2">
                Decisão <Tip term={TERMS.decision} />
              </p>
              <DecisionBadge decision={a.decision} className="px-2.5 py-1 text-base" />
            </div>
            <div>
              <p className="flex items-center gap-1 text-sm text-ink-2">
                Nota final <Tip term={TERMS.final} />
              </p>
              <p className="num text-[2.25rem] font-semibold leading-none tracking-tight">{a.score_final ?? "—"}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="flex items-center justify-between gap-4 text-sm text-ink-2">
                <span className="flex items-center gap-1">
                  Qualidade <Tip term={TERMS.quality} />
                </span>
                <ScoreMeter score={a.score_quality} inconclusive={a.quality_inconclusive} />
              </span>
              <span className="flex items-center justify-between gap-4 text-sm text-ink-2">
                <span className="flex items-center gap-1">
                  Preço <Tip term={TERMS.price} />
                </span>
                <ScoreMeter score={a.score_price} inconclusive={a.price_inconclusive} />
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

      {isStock && <SectionNav hasHistory={a.history.length > 0} />}

      {isStock && (
        <SectionTitle id="regras" title="Análise por regras" term={TERMS.rules}>
          Qualidade com médias e crescimento de 5 anos (ROE, margem, payout, FCO/lucro, CAGR); preço com os múltiplos atuais, o DY médio de 5 anos e a MM200.
          Cada indicador é pontuado entre uma faixa ruim e uma ótima.
        </SectionTitle>
      )}

      {isStock ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-5">
            <IndicatorTable title="Qualidade" term={TERMS.quality} score={a.score_quality} inconclusive={a.quality_inconclusive} stale={a.stale} rows={quality} />
            {a.technical ? (
              <IndicatorTable
                title="Preço — fundamentalista"
                term={TERMS.fundamentalPrice}
                score={a.score_price_fundamental}
                inconclusive={a.price_inconclusive}
                stale={a.stale}
                rows={price}
              />
            ) : (
              <IndicatorTable title="Preço" term={TERMS.price} score={a.score_price} inconclusive={a.price_inconclusive} stale={a.stale} rows={price} />
            )}
            <TechnicalPanel a={a} />
          </div>
          <div className="flex flex-col gap-5">
            <Eliminatory a={a} />
            <Panel>
              <PanelHeader title="Preço justo e preço teto" />
              <div className="px-4 pb-4">
                <PriceScale a={a} />
                <ValuationCalc a={a} />
              </div>
            </Panel>
          </div>
        </div>
      ) : null}

      {isStock && (
        <SectionTitle title="Dados da empresa" term={TERMS.panel}>
          Indicadores atuais, cotação, resultados e dividendos ano a ano.
        </SectionTitle>
      )}
      {isStock && a.fundamentals.length > 0 && <IndicatorPanel a={a} />}
      <PricePanel ticker={a.ticker} />
      {isStock && <HistorySection a={a} />}

      <p className="text-sm text-muted">
        Dados contábeis: {a.fundamentals_ref ?? "—"}
        {a.fundamentals_date && ` (data-base ${formatDate(a.fundamentals_date)})`} · Cotação de {formatDate(a.price_date)} · Regras v4 (pesos por setor + MM200, revisão em 30/04/2027).
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
