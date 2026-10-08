import * as React from "react";
import { ClipboardPaste, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAssetSearch, useCreateTransactionsBatch } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { TransactionInput, ValidationIssue } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatBRL, parseDecimalInput, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Row {
  key: number;
  date: string;
  type: "BUY" | "SELL";
  ticker: string;
  quantity: string;
  price: string;
  costs: string;
  broker: string;
}

let rowKey = 0;
const emptyRow = (date: string, broker = ""): Row => ({ key: ++rowKey, date, type: "BUY", ticker: "", quantity: "", price: "", costs: "", broker });

type RowErrors = Partial<Record<keyof Row, string>>;

function validateRow(r: Row, today: string): RowErrors {
  const e: RowErrors = {};
  if (!r.date) e.date = "Data obrigatória";
  else if (r.date > today) e.date = "Data no futuro";
  if (!/^[A-Z]{4}\d{1,2}F?$/.test(r.ticker)) e.ticker = "Ticker inválido";
  if (!(Number(parseDecimalInput(r.quantity)) > 0)) e.quantity = "Quantidade inválida";
  if (!(Number(parseDecimalInput(r.price)) > 0)) e.price = "Preço inválido";
  if (r.costs && parseDecimalInput(r.costs) === null) e.costs = "Valor inválido";
  return e;
}

const isBlank = (r: Row) => !r.ticker && !r.quantity && !r.price && !r.costs;

/** Parses rows pasted from a spreadsheet: data, tipo, ticker, quantidade, preço[, custos[, corretora]]. */
function parsePasted(text: string, today: string): Row[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.split("\t").map((c) => c.trim()))
    .filter((cells) => cells.length >= 5)
    .map((c) => {
      const br = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(c[0]);
      return {
        ...emptyRow(today),
        date: br ? `${br[3]}-${br[2]}-${br[1]}` : c[0],
        type: /^v/i.test(c[1]) ? "SELL" : "BUY",
        ticker: c[2].toUpperCase(),
        quantity: c[3],
        price: c[4],
        costs: c[5] ?? "",
        broker: c[6] ?? "",
      } satisfies Row;
    });
}

const cellClass =
  "h-8 w-full rounded-sm border border-transparent bg-transparent px-2 text-base hover:border-line-strong focus:border-ink focus:bg-surface focus:outline-none aria-[invalid=true]:border-down aria-[invalid=true]:bg-down-soft/40";

export function BatchDialog({ open, onOpenChange, today }: { open: boolean; onOpenChange: (o: boolean) => void; today: string }) {
  const [rows, setRows] = React.useState<Row[]>(() => [emptyRow(today), emptyRow(today), emptyRow(today)]);
  const [showErrors, setShowErrors] = React.useState(false);
  const [serverErrors, setServerErrors] = React.useState<Record<string, string>>({});
  const batch = useCreateTransactionsBatch();
  const universe = useAssetSearch("", open);

  React.useEffect(() => {
    if (open) {
      setRows([emptyRow(today), emptyRow(today), emptyRow(today)]);
      setShowErrors(false);
      setServerErrors({});
    }
  }, [open, today]);

  const filled = rows.filter((r) => !isBlank(r));
  const errorsByKey = new Map(rows.map((r) => [r.key, isBlank(r) ? {} : validateRow(r, today)]));
  const invalidCount = filled.filter((r) => Object.keys(errorsByKey.get(r.key)!).length > 0).length;
  const totals = filled.reduce(
    (acc, r) => {
      const v = (toNumber(parseDecimalInput(r.quantity)) ?? 0) * (toNumber(parseDecimalInput(r.price)) ?? 0);
      if (r.type === "BUY") acc.buy += v;
      else acc.sell += v;
      return acc;
    },
    { buy: 0, sell: 0 },
  );

  const update = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const remove = (key: number) => setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.key !== key) : rs));
  const add = () => setRows((rs) => [...rs, emptyRow(rs.at(-1)?.date ?? today, rs.at(-1)?.broker)]);

  const onPaste = (e: React.ClipboardEvent) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t")) return;
    const parsed = parsePasted(text, today);
    if (!parsed.length) return;
    e.preventDefault();
    setRows((rs) => [...rs.filter((r) => !isBlank(r)), ...parsed]);
    toast.success(`${parsed.length} linhas coladas da planilha.`);
  };

  const save = () => {
    setShowErrors(true);
    if (!filled.length) {
      toast.error("Preencha pelo menos uma linha.");
      return;
    }
    if (invalidCount) return;
    const inputs: TransactionInput[] = filled.map((r) => ({
      date: r.date,
      type: r.type,
      ticker: r.ticker,
      quantity: parseDecimalInput(r.quantity)!,
      price: parseDecimalInput(r.price),
      costs: parseDecimalInput(r.costs),
      broker: r.broker.trim() || null,
    }));
    batch.mutate(inputs, {
      onSuccess: (created) => {
        toast.success(created.length === 1 ? "1 lançamento salvo." : `${created.length} lançamentos salvos.`);
        onOpenChange(false);
      },
      onError: (err) => {
        if (err instanceof ApiError && Array.isArray(err.detail)) {
          const mapped: Record<string, string> = {};
          for (const issue of err.detail as ValidationIssue[]) {
            const [index, field] = issue.field.split(".");
            const row = filled[Number(index)];
            if (row) mapped[`${row.key}.${field}`] = issue.message;
          }
          setServerErrors(mapped);
        }
        toast.error(err.message);
      },
    });
  };

  const err = (r: Row, field: keyof Row) =>
    serverErrors[`${r.key}.${field}`] ?? (showErrors ? errorsByKey.get(r.key)?.[field] : undefined);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>Lançamento em lote</DialogTitle>
          <DialogDescription>
            Digite várias compras e vendas e salve tudo de uma vez. Dá para colar linhas de uma planilha (data, tipo, ticker, quantidade, preço, custos, corretora).
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="px-0 py-0" onPaste={onPaste}>
          <datalist id="batch-tickers">
            {(universe.data ?? []).map((a) => (
              <option key={a.ticker} value={a.ticker}>
                {a.name}
              </option>
            ))}
          </datalist>
          <table className="w-full min-w-[820px] border-collapse text-base">
            <thead className="sticky top-0 z-10 bg-surface-2">
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="w-10 py-2 pl-5 font-medium">#</th>
                <th className="w-40 px-1 font-medium">Data</th>
                <th className="w-28 px-1 font-medium">Tipo</th>
                <th className="w-28 px-1 font-medium">Ticker</th>
                <th className="w-24 px-1 text-right font-medium">Quant.</th>
                <th className="w-28 px-1 text-right font-medium">Preço</th>
                <th className="w-24 px-1 text-right font-medium">Custos</th>
                <th className="px-1 font-medium">Corretora</th>
                <th className="w-28 px-1 text-right font-medium">Total</th>
                <th className="w-12 pr-5" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const total = (toNumber(parseDecimalInput(r.quantity)) ?? 0) * (toNumber(parseDecimalInput(r.price)) ?? 0);
                const rowErrors = (["date", "ticker", "quantity", "price", "costs"] as const).map((f) => err(r, f)).filter(Boolean);
                return (
                  <React.Fragment key={r.key}>
                    <tr className={cn("border-b border-line", rowErrors.length && "border-b-0")}>
                      <td className="num py-1 pl-5 text-sm text-muted">{i + 1}</td>
                      <td className="px-1">
                        <input type="date" aria-label={`Data da linha ${i + 1}`} className={cellClass} value={r.date} max={today} onChange={(e) => update(r.key, { date: e.target.value })} aria-invalid={!!err(r, "date")} />
                      </td>
                      <td className="px-1">
                        <select aria-label={`Tipo da linha ${i + 1}`} className={cn(cellClass, r.type === "SELL" && "text-down")} value={r.type} onChange={(e) => update(r.key, { type: e.target.value as Row["type"] })}>
                          <option value="BUY">Compra</option>
                          <option value="SELL">Venda</option>
                        </select>
                      </td>
                      <td className="px-1">
                        <input aria-label={`Ticker da linha ${i + 1}`} list="batch-tickers" className={cn(cellClass, "font-semibold uppercase")} value={r.ticker} onChange={(e) => update(r.key, { ticker: e.target.value.toUpperCase().trim() })} placeholder="PETR4" aria-invalid={!!err(r, "ticker")} />
                      </td>
                      <td className="px-1">
                        <input aria-label={`Quantidade da linha ${i + 1}`} inputMode="decimal" className={cn(cellClass, "num text-right")} value={r.quantity} onChange={(e) => update(r.key, { quantity: e.target.value })} aria-invalid={!!err(r, "quantity")} />
                      </td>
                      <td className="px-1">
                        <input aria-label={`Preço da linha ${i + 1}`} inputMode="decimal" className={cn(cellClass, "num text-right")} value={r.price} onChange={(e) => update(r.key, { price: e.target.value })} placeholder="0,00" aria-invalid={!!err(r, "price")} />
                      </td>
                      <td className="px-1">
                        <input aria-label={`Custos da linha ${i + 1}`} inputMode="decimal" className={cn(cellClass, "num text-right")} value={r.costs} onChange={(e) => update(r.key, { costs: e.target.value })} placeholder="0,00" aria-invalid={!!err(r, "costs")} />
                      </td>
                      <td className="px-1">
                        <input aria-label={`Corretora da linha ${i + 1}`} className={cellClass} value={r.broker} onChange={(e) => update(r.key, { broker: e.target.value })} />
                      </td>
                      <td className="num px-1 text-right text-ink-2">{total ? formatBRL(total) : "—"}</td>
                      <td className="pr-5 text-right">
                        <Button variant="ghost" size="icon-sm" aria-label={`Remover linha ${i + 1}`} onClick={() => remove(r.key)}>
                          <Trash2 />
                        </Button>
                      </td>
                    </tr>
                    {rowErrors.length > 0 && (
                      <tr className="border-b border-line">
                        <td />
                        <td colSpan={9} className="pb-2 pl-1 text-sm text-down">
                          {rowErrors.join(" · ")}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center gap-3 px-5 py-3">
            <Button size="sm" onClick={add}>
              <Plus /> Adicionar linha
            </Button>
            <span className="inline-flex items-center gap-1.5 text-sm text-muted">
              <ClipboardPaste className="size-4" /> Ctrl+V cola linhas copiadas de uma planilha
            </span>
          </div>
        </DialogBody>
        <DialogFooter className="justify-between">
          <span className="text-sm text-ink-2">
            {filled.length} {filled.length === 1 ? "linha" : "linhas"} · compras <span className="num font-medium text-ink">{formatBRL(totals.buy)}</span> · vendas{" "}
            <span className="num font-medium text-ink">{formatBRL(totals.sell)}</span>
            {showErrors && invalidCount > 0 && <span className="ml-2 text-down">· {invalidCount} com erro</span>}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={save} disabled={batch.isPending}>
              {batch.isPending ? "Salvando…" : filled.length === 1 ? "Salvar 1 lançamento" : filled.length ? `Salvar ${filled.length} lançamentos` : "Salvar lançamentos"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
