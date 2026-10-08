import * as React from "react";
import { Link } from "react-router-dom";
import { CircleAlert, RotateCw } from "lucide-react";
import type { PendingItem, SourceWarning } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/misc";
import { formatDate, formatDateTimeShort } from "@/lib/format";

export function PageTitle({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function QueryError({ error, onRetry, what }: { error: Error; onRetry: () => void; what: string }) {
  return (
    <Callout
      tone="error"
      title={`Não foi possível carregar ${what}.`}
      action={
        <Button size="sm" onClick={onRetry}>
          <RotateCw /> Tentar de novo
        </Button>
      }
    >
      {error.message}
    </Callout>
  );
}

/** External sources that failed: the page keeps working with the last cached data. */
export function SourceWarnings({ warnings }: { warnings: SourceWarning[] | undefined }) {
  if (!warnings?.length) return null;
  return (
    <div className="mb-4 flex flex-col gap-2">
      {warnings.map((w) => (
        <Callout key={w.source} tone="warn" title={`${w.source} indisponível. Mostrando os últimos dados salvos.`}>
          {w.message}
          {w.last_success_at && ` Última atualização: ${formatDateTimeShort(w.last_success_at)}.`}
        </Callout>
      ))}
    </div>
  );
}

const PENDING_TITLE: Record<PendingItem["kind"], string> = {
  BONUS_NO_COST: "Bonificação sem custo",
  POSSIBLE_DUPLICATE: "Possível duplicata",
  UNRECOGNIZED_EVENT: "Evento não reconhecido",
};

export function PendingBanner({ items }: { items: PendingItem[] | undefined }) {
  if (!items?.length) return null;
  return (
    <section aria-label="Pendências" className="mb-6 rounded-lg border border-warn/30 bg-warn-soft">
      <header className="flex items-center gap-2 px-4 pt-3 text-ink">
        <CircleAlert className="size-4 text-warn" />
        <h2 className="font-semibold">
          {items.length === 1 ? "1 pendência precisa da sua atenção" : `${items.length} pendências precisam da sua atenção`}
        </h2>
      </header>
      <ul className="divide-y divide-warn/20 px-4 pb-1">
        {items.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
            <span className="w-full shrink-0 text-sm font-medium text-warn sm:w-40">{PENDING_TITLE[p.kind]}</span>
            <span className="font-semibold">{p.ticker}</span>
            <span className="min-w-0 basis-full text-ink-2 sm:flex-1 sm:basis-0">{p.message}</span>
            <span className="num text-sm text-muted">{formatDate(p.date)}</span>
            <Button asChild size="sm" variant="secondary">
              <Link to={`/operacoes?ticker=${p.ticker}`}>{p.kind === "BONUS_NO_COST" ? "Informar custo" : "Revisar"}</Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export type RangeKey = "12m" | "24m" | "all";

export const RANGE_OPTIONS: { value: RangeKey; label: string }[] = [
  { value: "12m", label: "12 meses" },
  { value: "24m", label: "24 meses" },
  { value: "all", label: "Desde o início" },
];

export function rangeStart(range: RangeKey, today: string): string | null {
  if (range === "all") return null;
  const months = range === "12m" ? 12 : 24;
  const d = new Date(`${today}T12:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - months);
  return d.toISOString().slice(0, 10);
}

export function filterByRange<T extends { date: string }>(rows: T[], range: RangeKey, today: string): T[] {
  const start = rangeStart(range, today);
  return start ? rows.filter((r) => r.date >= start) : rows;
}
