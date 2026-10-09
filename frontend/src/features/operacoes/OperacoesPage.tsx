import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, CalendarRange, MoreHorizontal, Pencil, Plus, Rows3, Search, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import { useDeleteTransaction, useSummary, useTransactions } from "@/api/hooks";
import type { Source, Transaction, TransactionType } from "@/api/types";
import { Private, SourceBadge } from "@/components/domain";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/form";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Tooltip } from "@/components/ui/menu";
import { EmptyState, Panel, Skeleton } from "@/components/ui/misc";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatDate, formatNumber, formatQuantity } from "@/lib/format";
import { TX_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { PageTitle, QueryError } from "../shared";
import { BatchDialog } from "./BatchDialog";
import { TransactionDialog, type DialogMode } from "./TransactionDialog";

const TYPE_FILTERS: { value: TransactionType | "ALL" | "EVENTS" | "INCOME_ALL"; label: string }[] = [
  { value: "ALL", label: "Todos os tipos" },
  { value: "BUY", label: "Compras" },
  { value: "SELL", label: "Vendas" },
  { value: "EVENTS", label: "Eventos corporativos" },
  { value: "INCOME_ALL", label: "Proventos" },
];

const EVENT_TYPES: TransactionType[] = ["SPLIT", "REVERSE_SPLIT", "BONUS", "TICKER_CHANGE", "FRACTION_AUCTION"];
const INCOME_TYPES: TransactionType[] = ["DIVIDEND", "JCP", "INCOME"];

function typeTone(t: TransactionType) {
  if (t === "BUY") return "text-ink";
  if (t === "SELL" || t === "FRACTION_AUCTION") return "text-down";
  if (INCOME_TYPES.includes(t)) return "text-up";
  return "text-info";
}

/** Value column: trades show the financial total; events show the factor; proventos the net amount. */
function amountOf(t: Transaction): React.ReactNode {
  if (INCOME_TYPES.includes(t.type)) return formatBRL(t.net_amount);
  if (t.type === "SPLIT" || t.type === "REVERSE_SPLIT") return <span className="text-ink-2">fator {formatNumber(t.factor)}</span>;
  if (t.type === "BONUS" && !t.price) return <Badge tone="warn">sem custo</Badge>;
  if (t.price === null) return "—";
  const gross = Number(t.quantity) * Number(t.price);
  const costs = Number(t.costs ?? 0);
  return formatBRL(t.type === "SELL" ? gross - costs : gross + costs);
}

export function OperacoesPage() {
  const [params, setParams] = useSearchParams();
  const summary = useSummary();
  const today = summary.data?.as_of ?? new Date().toISOString().slice(0, 10);
  const [ticker, setTicker] = React.useState(params.get("ticker") ?? "");
  const [type, setType] = React.useState<(typeof TYPE_FILTERS)[number]["value"]>("ALL");
  const [source, setSource] = React.useState<Source | "ALL">(() => {
    const s = params.get("source");
    return s === "MANUAL" || s === "B3" || s === "AUTO" ? s : "ALL";
  });
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [limit, setLimit] = React.useState(40);
  const [dialog, setDialog] = React.useState<{ mode: DialogMode; tx: Transaction | null } | null>(null);
  const [batchOpen, setBatchOpen] = React.useState(false);
  const [toDelete, setToDelete] = React.useState<Transaction | null>(null);
  const del = useDeleteTransaction();

  const query = useTransactions({
    ticker: ticker.trim() || undefined,
    type: type === "EVENTS" || type === "INCOME_ALL" ? "ALL" : type,
    source,
    from: from || undefined,
    to: to || undefined,
  });

  const rows = (query.data ?? []).filter((t) =>
    type === "EVENTS" ? EVENT_TYPES.includes(t.type) : type === "INCOME_ALL" ? INCOME_TYPES.includes(t.type) : true,
  );
  const duplicates = rows.filter((t) => t.possible_duplicate).length;
  const filtersActive = ticker || type !== "ALL" || source !== "ALL" || from || to;

  const clearFilters = () => {
    setTicker("");
    setType("ALL");
    setSource("ALL");
    setFrom("");
    setTo("");
    if (params.has("ticker") || params.has("source")) setParams({}, { replace: true });
  };

  const confirmDelete = () => {
    if (!toDelete) return;
    del.mutate(toDelete.id, {
      onSuccess: () => {
        toast.success(`Lançamento de ${toDelete.ticker} excluído. A carteira foi recalculada.`);
        setToDelete(null);
      },
      onError: (e) => toast.error(e.message),
    });
  };

  return (
    <>
      <PageTitle
        title="Operações"
        description="O livro de lançamentos. Posição, preço médio e proventos são calculados a partir dele."
        actions={
          <>
            <Button onClick={() => setBatchOpen(true)}>
              <Rows3 /> Lançamento em lote
            </Button>
            <Button onClick={() => setDialog({ mode: "EVENT", tx: null })}>
              <Zap /> Lançar evento
            </Button>
            <Button onClick={() => setDialog({ mode: "SELL", tx: null })}>Lançar venda</Button>
            <Button variant="primary" onClick={() => setDialog({ mode: "BUY", tx: null })}>
              <Plus /> Lançar compra
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-52">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input aria-label="Filtrar por ticker" placeholder="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} className="pl-8 uppercase placeholder:normal-case" />
        </div>
        <NativeSelect aria-label="Tipo" value={type} onChange={(e) => setType(e.target.value as typeof type)} className="w-auto min-w-44">
          {TYPE_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Origem" value={source} onChange={(e) => setSource(e.target.value as Source | "ALL")} className="w-auto min-w-40">
          <option value="ALL">Todas as origens</option>
          <option value="MANUAL">Manual</option>
          <option value="B3">Importado da B3</option>
          <option value="AUTO">Automático</option>
        </NativeSelect>
        <div className="flex items-center gap-1.5">
          <CalendarRange className="size-4 text-muted" />
          <Input type="date" aria-label="De" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" />
          <span className="text-muted">até</span>
          <Input type="date" aria-label="Até" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" />
        </div>
        {filtersActive && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Limpar filtros
          </Button>
        )}
      </div>

      {duplicates > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-warn/30 bg-warn-soft px-3 py-2 text-sm">
          <AlertTriangle className="size-4 text-warn" />
          {duplicates === 1 ? "1 lançamento parece duplicado" : `${duplicates} lançamentos parecem duplicados`} de uma linha importada. Revise e exclua o que estiver repetido. Nada é apagado automaticamente.
        </div>
      )}

      {query.isError ? (
        <QueryError what="os lançamentos" error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <Panel className={cn("transition-opacity", query.isFetching && query.data && "opacity-60")}>
          {query.isPending ? (
            <div className="flex flex-col gap-2 p-4">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={Rows3}
              title={filtersActive ? "Nenhum lançamento com esses filtros" : "Nenhum lançamento ainda"}
              action={
                filtersActive ? (
                  <Button onClick={clearFilters}>Limpar filtros</Button>
                ) : (
                  <Button variant="primary" onClick={() => setDialog({ mode: "BUY", tx: null })}>
                    <Plus /> Lançar compra
                  </Button>
                )
              }
            >
              {filtersActive ? "Mude ou limpe os filtros para ver outros lançamentos." : "Lance sua primeira compra ou importe o extrato de negociação da B3."}
            </EmptyState>
          ) : (
            <>
              <Table>
                <THead>
                  <TR className="bg-surface-2">
                    <TH>Data</TH>
                    <TH>Ativo</TH>
                    <TH>Tipo</TH>
                    <TH numeric>Quant.</TH>
                    <TH numeric>Preço</TH>
                    <TH numeric>Custos</TH>
                    <TH numeric>Valor</TH>
                    <TH>Corretora</TH>
                    <TH>Origem</TH>
                    <TH className="w-10">
                      <span className="sr-only">Ações</span>
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {rows.slice(0, limit).map((t) => (
                    <TR key={t.id} className={cn("hover:bg-surface-2", t.possible_duplicate && "bg-warn-soft/60 hover:bg-warn-soft")}>
                      <TD className="num">{formatDate(t.date)}</TD>
                      <TD>
                        <span className="font-semibold">{t.ticker}</span>
                        {t.target_ticker && <span className="text-ink-2"> → {t.target_ticker}</span>}
                      </TD>
                      <TD>
                        <span className={cn("font-medium", typeTone(t.type))}>{TX_TYPE_LABEL[t.type]}</span>
                        {t.possible_duplicate && (
                          <Tooltip content="Mesma data, ticker, tipo e quantidade de uma linha importada da B3.">
                            <Badge tone="warn" className="ml-2">
                              Possível duplicata
                            </Badge>
                          </Tooltip>
                        )}
                        {t.note && <div className="max-w-56 truncate text-sm text-muted">{t.note}</div>}
                      </TD>
                      <TD numeric><Private>{formatQuantity(t.quantity)}</Private></TD>
                      <TD numeric>{t.price ? formatBRL(t.price, { precise: INCOME_TYPES.includes(t.type) }) : "—"}</TD>
                      <TD numeric className="text-ink-2"><Private>{t.costs ? formatBRL(t.costs) : "—"}</Private></TD>
                      <TD numeric className="font-medium"><Private>{amountOf(t)}</Private></TD>
                      <TD className="max-w-40 truncate text-ink-2">{t.broker ?? "—"}</TD>
                      <TD>
                        <SourceBadge source={t.source} edited={t.user_edited} />
                      </TD>
                      <TD className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon-sm" aria-label={`Ações do lançamento de ${t.ticker} em ${formatDate(t.date)}`}>
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setDialog({ mode: t.type === "SELL" ? "SELL" : t.type === "BUY" ? "BUY" : "EVENT", tx: t })}>
                              <Pencil /> Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem danger onSelect={() => setToDelete(t)}>
                              <Trash2 /> Excluir
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
                <span>
                  {Math.min(limit, rows.length)} de {rows.length} lançamentos
                </span>
                {rows.length > limit && (
                  <Button variant="ghost" size="sm" onClick={() => setLimit((l) => l + 60)}>
                    Mostrar mais
                  </Button>
                )}
              </div>
            </>
          )}
        </Panel>
      )}

      {dialog && (
        <TransactionDialog
          open={Boolean(dialog)}
          onOpenChange={(o) => !o && setDialog(null)}
          mode={dialog.mode}
          transaction={dialog.tx}
          today={today}
        />
      )}
      <BatchDialog open={batchOpen} onOpenChange={setBatchOpen} today={today} />

      <Dialog open={Boolean(toDelete)} onOpenChange={(o) => !o && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir lançamento?</DialogTitle>
            <DialogDescription>
              {toDelete && (
                <>
                  {TX_TYPE_LABEL[toDelete.type]} de {formatQuantity(toDelete.quantity)} {toDelete.ticker} em {formatDate(toDelete.date)}. A posição, o preço médio e os proventos afetados serão recalculados.
                  {toDelete.source === "AUTO" && " Este lançamento foi gerado automaticamente e pode voltar na próxima atualização se continuar válido."}
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setToDelete(null)}>
              Cancelar
            </Button>
            <Button variant="danger" onClick={confirmDelete} disabled={del.isPending}>
              {del.isPending ? "Excluindo…" : "Excluir lançamento"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
