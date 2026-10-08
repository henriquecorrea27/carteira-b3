import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Search, Wallet } from "lucide-react";
import { usePositions } from "@/api/hooks";
import type { AssetClass, Position } from "@/api/types";
import { AllocationBars } from "@/components/charts/AllocationStrip";
import { AssetCell, DecisionBadge, Delta, ScoreMeter } from "@/components/domain";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Tooltip } from "@/components/ui/menu";
import { EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { SortHeader, TBody, TD, TH, THead, TR, Table, type SortDir } from "@/components/ui/table";
import { formatBRL, formatPct, formatQuantity } from "@/lib/format";
import { ASSET_CLASS_LABEL, ASSET_CLASS_ORDER } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { QueryError } from "../shared";

type SortKey = "ticker" | "market_value" | "weight_pct" | "pnl_pct" | "day_change_pct" | "yield_on_cost_pct" | "score";
type ClassFilter = AssetClass | "ALL";

function sortValue(p: Position, key: SortKey): number | string {
  if (key === "ticker") return p.ticker;
  if (key === "score") return p.rules?.score_final ?? -1;
  return Number(p[key] ?? -Infinity);
}

function ClassGroup({
  assetClass,
  rows,
  totalValue,
  sort,
  onSort,
}: {
  assetClass: AssetClass;
  rows: Position[];
  totalValue: number;
  sort: { key: SortKey; dir: SortDir };
  onSort: (key: SortKey) => void;
}) {
  const navigate = useNavigate();
  const isStock = assetClass === "STOCK";
  const value = rows.reduce((a, r) => a + Number(r.market_value), 0);
  const cost = rows.reduce((a, r) => a + Number(r.cost_basis), 0);
  const pnl = value - cost;

  const sorted = [...rows].sort((a, b) => {
    const va = sortValue(a, sort.key);
    const vb = sortValue(b, sort.key);
    const cmp = typeof va === "string" ? va.localeCompare(vb as string) : va - (vb as number);
    return sort.dir === "asc" ? cmp : -cmp;
  });

  const header = (key: SortKey, label: string, numeric = true) => (
    <TH numeric={numeric} className="group/th" aria-sort={sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <SortHeader label={label} numeric={numeric} active={sort.key === key} dir={sort.dir} onClick={() => onSort(key)} />
    </TH>
  );

  return (
    <Panel>
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-4 pb-3 pt-4">
        <h2 className="text-lg font-semibold">
          {ASSET_CLASS_LABEL[assetClass]} <span className="font-normal text-muted">{rows.length}</span>
        </h2>
        <dl className="ml-auto flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-ink-2">Valor</dt>
            <dd className="num font-semibold">{formatBRL(value)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-ink-2">Resultado</dt>
            <dd>
              <Delta value={pnl} kind="brl" arrow={false} className="font-semibold" />{" "}
              <Delta value={cost ? (pnl / cost) * 100 : 0} arrow={false} className="text-ink-2" />
            </dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-ink-2">Na carteira</dt>
            <dd className="num font-semibold">{formatPct((value / totalValue) * 100, { decimals: 1 })}</dd>
          </div>
        </dl>
      </header>
      <Table>
        <THead>
          <TR className="bg-surface-2">
            {header("ticker", "Ativo", false)}
            <TH numeric>Quant.</TH>
            <TH numeric>Preço médio</TH>
            <TH numeric>Preço atual</TH>
            {header("day_change_pct", "Dia")}
            {header("market_value", "Valor")}
            {header("weight_pct", "% carteira")}
            {header("pnl_pct", "Resultado")}
            {header("yield_on_cost_pct", "Yield on cost")}
            <TH numeric>Proventos</TH>
            {isStock && header("score", "Nota")}
            {isStock && <TH>Decisão</TH>}
          </TR>
        </THead>
        <TBody>
          {sorted.map((p) => (
            <TR
              key={p.ticker}
              className={cn("group", isStock && "cursor-pointer hover:bg-surface-2")}
              onClick={isStock ? () => navigate(`/analise/${p.ticker}`) : undefined}
            >
              <TD>
                <AssetCell ticker={p.ticker} name={p.name} assetClass={p.asset_class} />
              </TD>
              <TD numeric>{formatQuantity(p.quantity)}</TD>
              <TD numeric>
                <span className="inline-flex items-center gap-1">
                  {p.pending_cost && (
                    <Tooltip content="Bonificação sem custo atribuído: o preço médio é provisório até você informar o valor.">
                      <AlertTriangle className="size-3.5 text-warn" aria-label="Preço médio provisório" />
                    </Tooltip>
                  )}
                  {formatBRL(p.avg_price)}
                </span>
              </TD>
              <TD numeric>{formatBRL(p.last_price)}</TD>
              <TD numeric>
                <Delta value={p.day_change_pct} arrow={false} />
              </TD>
              <TD numeric className="font-medium">{formatBRL(p.market_value)}</TD>
              <TD numeric>{formatPct(p.weight_pct, { decimals: 1 })}</TD>
              <TD numeric>
                <div className="flex flex-col items-end leading-tight">
                  <Delta value={p.pnl_pct} />
                  <span className="text-sm text-ink-2">{formatBRL(p.pnl, { signed: true })}</span>
                </div>
              </TD>
              <TD numeric>{formatPct(p.yield_on_cost_pct, { decimals: 1 })}</TD>
              <TD numeric>{formatBRL(p.dividends_received)}</TD>
              {isStock && (
                <TD numeric>
                  {p.rules ? <ScoreMeter score={p.rules.score_final} inconclusive={p.rules.inconclusive} /> : "—"}
                </TD>
              )}
              {isStock && <TD>{p.rules ? <DecisionBadge decision={p.rules.decision} /> : <span className="text-muted">—</span>}</TD>}
            </TR>
          ))}
        </TBody>
      </Table>
    </Panel>
  );
}

export function PosicoesView() {
  const positions = usePositions();
  const [query, setQuery] = React.useState("");
  const [cls, setCls] = React.useState<ClassFilter>("ALL");
  const [sort, setSort] = React.useState<{ key: SortKey; dir: SortDir }>({ key: "market_value", dir: "desc" });

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "ticker" ? "asc" : "desc" }));

  if (positions.isError) return <QueryError what="as posições" error={positions.error} onRetry={() => positions.refetch()} />;
  if (positions.isPending)
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-96 w-full" />
      </div>
    );

  const all = positions.data;
  if (all.length === 0)
    return (
      <Panel>
        <EmptyState
          icon={Wallet}
          title="Sua carteira está vazia"
          action={
            <Button asChild variant="primary">
              <Link to="/operacoes">Lançar primeira compra</Link>
            </Button>
          }
        >
          Lance uma compra ou importe o extrato de negociação da B3 para ver suas posições aqui.
        </EmptyState>
      </Panel>
    );

  const totalValue = all.reduce((a, p) => a + Number(p.market_value), 0);
  const q = query.trim().toUpperCase();
  const visible = all.filter((p) => (cls === "ALL" || p.asset_class === cls) && (!q || p.ticker.includes(q) || p.name.toUpperCase().includes(q)));
  const classes = ASSET_CLASS_ORDER.filter((c) => all.some((p) => p.asset_class === c));

  const bySector = new Map<string, number>();
  const byClass = new Map<string, number>();
  for (const p of all) {
    bySector.set(p.sector ?? "Sem setor", (bySector.get(p.sector ?? "Sem setor") ?? 0) + Number(p.market_value));
    byClass.set(ASSET_CLASS_LABEL[p.asset_class], (byClass.get(ASSET_CLASS_LABEL[p.asset_class]) ?? 0) + Number(p.market_value));
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filtrar por ticker ou nome"
            className="pl-8"
            aria-label="Filtrar posições"
          />
        </div>
        <Segmented
          aria-label="Classe de ativo"
          value={cls}
          onChange={setCls}
          options={[{ value: "ALL", label: "Todas" }, ...classes.map((c) => ({ value: c, label: ASSET_CLASS_LABEL[c] }))]}
        />
      </div>

      {classes
        .filter((c) => visible.some((p) => p.asset_class === c))
        .map((c) => (
          <ClassGroup
            key={c}
            assetClass={c}
            rows={visible.filter((p) => p.asset_class === c)}
            totalValue={totalValue}
            sort={sort}
            onSort={onSort}
          />
        ))}
      {visible.length === 0 && (
        <Panel>
          <EmptyState icon={Search} title="Nenhum ativo encontrado">
            Nenhuma posição corresponde a “{query}”.
          </EmptyState>
        </Panel>
      )}

      <div className="grid items-start gap-5 md:grid-cols-2">
        <Panel>
          <PanelHeader title="Por classe" />
          <AllocationBars className="px-4 pb-5" slices={[...byClass].map(([k, v]) => ({ key: k, label: k, value: v }))} />
        </Panel>
        <Panel>
          <PanelHeader title="Por setor" />
          <AllocationBars className="px-4 pb-5" slices={[...bySector].map(([k, v]) => ({ key: k, label: k, value: v }))} />
        </Panel>
      </div>
    </div>
  );
}
