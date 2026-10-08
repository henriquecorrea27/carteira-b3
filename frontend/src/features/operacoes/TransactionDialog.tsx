import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useCreateTransaction, usePositions, useUpdateTransaction } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { Transaction, TransactionInput, TransactionType, ValidationIssue } from "@/api/types";
import { TickerCombobox } from "@/components/TickerCombobox";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form";
import { formatBRL, parseDecimalInput, toNumber } from "@/lib/format";
import { TX_TYPE_LABEL } from "@/lib/labels";

export type DialogMode = "BUY" | "SELL" | "EVENT";

const EVENT_TYPES: TransactionType[] = ["SPLIT", "REVERSE_SPLIT", "BONUS", "TICKER_CHANGE", "FRACTION_AUCTION"];
const PROVENTO_TYPES: TransactionType[] = ["DIVIDEND", "JCP", "INCOME"];

const EVENT_HELP: Partial<Record<TransactionType, string>> = {
  SPLIT: "Cada ação vira k ações. A quantidade é multiplicada por k e o preço médio dividido por k.",
  REVERSE_SPLIT: "k ações viram 1. A quantidade é dividida por k e o preço médio multiplicado por k.",
  BONUS: "Ações novas recebidas. O custo atribuído está no aviso aos acionistas da empresa.",
  TICKER_CHANGE: "Converte a posição para outro ticker, preservando o custo total.",
  FRACTION_AUCTION: "Fração vendida em leilão após um grupamento ou bonificação; conta como venda.",
};

interface FormState {
  date: string;
  ticker: string;
  type: TransactionType;
  quantity: string;
  price: string;
  costs: string;
  factor: string;
  target_ticker: string;
  broker: string;
  note: string;
}

function initialState(mode: DialogMode, tx: Transaction | null, today: string): FormState {
  const ptBR = (v: string | null) => (v ? v.replace(".", ",") : "");
  if (tx)
    return {
      date: tx.date,
      ticker: tx.ticker,
      type: tx.type,
      quantity: ptBR(tx.quantity),
      price: ptBR(tx.price),
      costs: ptBR(tx.costs),
      factor: ptBR(tx.factor),
      target_ticker: tx.target_ticker ?? "",
      broker: tx.broker ?? "",
      note: tx.note ?? "",
    };
  return {
    date: today,
    ticker: "",
    type: mode === "EVENT" ? "SPLIT" : mode,
    quantity: "",
    price: "",
    costs: "",
    factor: "",
    target_ticker: "",
    broker: "",
    note: "",
  };
}

export function TransactionDialog({
  open,
  onOpenChange,
  mode,
  transaction,
  today,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: DialogMode;
  transaction: Transaction | null;
  today: string;
}) {
  const [form, setForm] = React.useState<FormState>(() => initialState(mode, transaction, today));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const positions = usePositions();
  const saving = create.isPending || update.isPending;

  React.useEffect(() => {
    if (open) {
      setForm(initialState(mode, transaction, today));
      setErrors({});
    }
  }, [open, mode, transaction, today]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      const { [key]: _removed, ...rest } = e;
      void _removed;
      return rest;
    });
  };

  const isTrade = form.type === "BUY" || form.type === "SELL";
  const isProvento = PROVENTO_TYPES.includes(form.type);
  const needsFactor = form.type === "SPLIT" || form.type === "REVERSE_SPLIT" || form.type === "TICKER_CHANGE";
  const needsQuantity = !(form.type === "SPLIT" || form.type === "REVERSE_SPLIT" || form.type === "TICKER_CHANGE");
  const priceLabel = form.type === "BONUS" ? "Custo atribuído por ação" : form.type === "FRACTION_AUCTION" ? "Valor por ação no leilão" : isProvento ? "Valor por ação" : "Preço unitário";

  const qty = toNumber(parseDecimalInput(form.quantity));
  const price = toNumber(parseDecimalInput(form.price));
  const costs = toNumber(parseDecimalInput(form.costs)) ?? 0;
  const total = qty !== null && price !== null ? qty * price + (form.type === "BUY" ? costs : form.type === "SELL" ? -costs : 0) : null;

  // Typing-error guard: warn (never block) when the price is far from the last close.
  const lastClose = positions.data?.find((p) => p.ticker === form.ticker)?.last_price;
  const deviation = isTrade && price && lastClose ? Math.abs(price / Number(lastClose) - 1) : 0;
  const held = positions.data?.find((p) => p.ticker === form.ticker)?.quantity;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!form.date) local.date = "Informe a data.";
    else if (form.date > today) local.date = "A data não pode estar no futuro.";
    if (!form.ticker) local.ticker = "Escolha o ativo.";
    if (needsQuantity && !(qty && qty > 0)) local.quantity = "Informe uma quantidade maior que zero.";
    if ((isTrade || form.type === "FRACTION_AUCTION") && !(price && price > 0)) local.price = "Informe o preço.";
    if (form.price && price === null) local.price = "Valor inválido. Use o formato 12,34.";
    if (form.costs && parseDecimalInput(form.costs) === null) local.costs = "Valor inválido.";
    if (needsFactor && !(toNumber(parseDecimalInput(form.factor)) ?? 0)) local.factor = "Informe o fator.";
    if (form.type === "TICKER_CHANGE" && !form.target_ticker) local.target_ticker = "Informe o novo ticker.";
    setErrors(local);
    if (Object.keys(local).length) return;

    const input: TransactionInput = {
      date: form.date,
      ticker: form.ticker,
      type: form.type,
      quantity: needsQuantity ? parseDecimalInput(form.quantity)! : "0",
      price: parseDecimalInput(form.price),
      costs: parseDecimalInput(form.costs),
      factor: needsFactor ? parseDecimalInput(form.factor) : null,
      target_ticker: form.type === "TICKER_CHANGE" ? form.target_ticker : null,
      broker: form.broker.trim() || null,
      note: form.note.trim() || null,
    };
    const onError = (err: Error) => {
      if (err instanceof ApiError && Array.isArray(err.detail)) {
        const mapped: Record<string, string> = {};
        for (const issue of err.detail as ValidationIssue[]) mapped[issue.field] = issue.message;
        setErrors(mapped);
      } else toast.error(err.message);
    };
    const done = (message: string) => {
      toast.success(message);
      onOpenChange(false);
    };
    const what = `${TX_TYPE_LABEL[form.type].toLowerCase()} de ${form.ticker}`;
    if (transaction) update.mutate({ id: transaction.id, input }, { onSuccess: () => done(`Alterações salvas: ${what}.`), onError });
    else create.mutate(input, { onSuccess: () => done(`Lançamento salvo: ${what}.`), onError });
  };

  const title = transaction
    ? `Editar ${TX_TYPE_LABEL[transaction.type].toLowerCase()}`
    : mode === "BUY"
      ? "Lançar compra"
      : mode === "SELL"
        ? "Lançar venda"
        : "Lançar evento";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {transaction?.source === "AUTO"
                ? "Lançamento automático. Sua edição prevalece: o job diário não vai sobrescrevê-la."
                : mode === "EVENT"
                  ? "Desdobramentos, grupamentos e bonificações normalmente entram sozinhos. Use isto para corrigir ou completar."
                  : "A posição e o preço médio são recalculados a partir dos lançamentos."}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="grid grid-cols-2 gap-4">
            {mode === "EVENT" && !transaction && (
              <Field label="Tipo de evento" htmlFor="tx-type" className="col-span-2" hint={EVENT_HELP[form.type]}>
                <NativeSelect id="tx-type" value={form.type} onChange={(e) => set("type", e.target.value as TransactionType)}>
                  {EVENT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {TX_TYPE_LABEL[t]}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            )}
            <Field label="Data" htmlFor="tx-date" error={errors.date}>
              <Input id="tx-date" type="date" value={form.date} max={today} onChange={(e) => set("date", e.target.value)} aria-invalid={!!errors.date} />
            </Field>
            <Field
              label="Ativo"
              htmlFor="tx-ticker"
              error={errors.ticker}
              hint={form.type === "SELL" && held ? `Você tem ${held.replace(".", ",")} hoje.` : undefined}
            >
              <TickerCombobox id="tx-ticker" value={form.ticker} onChange={(t) => set("ticker", t)} invalid={!!errors.ticker} />
            </Field>
            {needsQuantity && (
              <Field label={form.type === "BONUS" ? "Ações recebidas" : "Quantidade"} htmlFor="tx-qty" error={errors.quantity}>
                <Input id="tx-qty" inputMode="decimal" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} placeholder="0" aria-invalid={!!errors.quantity} className="num" />
              </Field>
            )}
            {needsFactor && (
              <Field
                label="Fator (k)"
                htmlFor="tx-factor"
                error={errors.factor}
                hint={form.type === "SPLIT" ? "Ex.: 2 para 1 ação virar 2" : form.type === "REVERSE_SPLIT" ? "Ex.: 10 para 10 ações virarem 1" : "Ações novas por ação antiga"}
              >
                <Input id="tx-factor" inputMode="decimal" value={form.factor} onChange={(e) => set("factor", e.target.value)} aria-invalid={!!errors.factor} className="num" />
              </Field>
            )}
            {form.type === "TICKER_CHANGE" && (
              <Field label="Novo ticker" htmlFor="tx-target" error={errors.target_ticker}>
                <TickerCombobox id="tx-target" value={form.target_ticker} onChange={(t) => set("target_ticker", t)} invalid={!!errors.target_ticker} />
              </Field>
            )}
            {!needsFactor && (
              <Field
                label={priceLabel}
                htmlFor="tx-price"
                error={errors.price}
                optional={form.type === "BONUS"}
                hint={form.type === "BONUS" ? "Sem o custo, o evento fica pendente e o preço médio aparece como provisório." : undefined}
              >
                <Input id="tx-price" inputMode="decimal" value={form.price} onChange={(e) => set("price", e.target.value)} placeholder="0,00" aria-invalid={!!errors.price} className="num" />
              </Field>
            )}
            {isTrade && (
              <Field label="Custos" htmlFor="tx-costs" optional error={errors.costs} hint="Corretagem, emolumentos e taxas">
                <Input id="tx-costs" inputMode="decimal" value={form.costs} onChange={(e) => set("costs", e.target.value)} placeholder="0,00" className="num" />
              </Field>
            )}
            {isTrade && (
              <Field label="Corretora" htmlFor="tx-broker" optional>
                <Input id="tx-broker" value={form.broker} onChange={(e) => set("broker", e.target.value)} list="brokers" />
                <datalist id="brokers">
                  <option value="XP Investimentos" />
                  <option value="Inter DTVM" />
                  <option value="BTG Pactual" />
                  <option value="Rico" />
                  <option value="Clear" />
                </datalist>
              </Field>
            )}
            <Field label="Observação" htmlFor="tx-note" optional className="col-span-2">
              <Textarea id="tx-note" rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} />
            </Field>

            {deviation > 0.2 && lastClose && (
              <div className="col-span-2 flex items-start gap-2 rounded-md border border-warn/30 bg-warn-soft px-3 py-2 text-sm">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />
                <span>
                  O preço está {Math.round(deviation * 100)}% longe do último fechamento ({formatBRL(lastClose)}). Confira se não houve erro de digitação.
                </span>
              </div>
            )}
          </DialogBody>
          <DialogFooter className="justify-between">
            <span className="text-sm text-ink-2">
              {isTrade && total !== null ? (
                <>
                  Total <span className="num font-semibold text-ink">{formatBRL(total)}</span>
                </>
              ) : null}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" disabled={saving}>
                {saving ? "Salvando…" : transaction ? "Salvar alterações" : title}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
