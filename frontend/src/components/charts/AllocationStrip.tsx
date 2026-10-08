import * as React from "react";
import { formatBRL, formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SERIES, SERIES_OTHER } from "./common";

export interface Slice {
  key: string;
  label: string;
  value: number;
}

/**
 * The portfolio as one segmented strip: each holding is a segment, separated by a 2px gap.
 * At most 8 colored slices; the rest fold into "Outros". The legend under it carries the values.
 */
export function AllocationStrip({ slices, maxSlices = 7, className }: { slices: Slice[]; maxSlices?: number; className?: string }) {
  const [hover, setHover] = React.useState<string | null>(null);
  const sorted = [...slices].sort((a, b) => b.value - a.value);
  const total = sorted.reduce((a, s) => a + s.value, 0) || 1;
  const head = sorted.slice(0, maxSlices);
  const tail = sorted.slice(maxSlices);
  const items = [
    ...head.map((s, i) => ({ ...s, color: SERIES[i] })),
    ...(tail.length
      ? [{ key: "__other", label: `Outros (${tail.length})`, value: tail.reduce((a, s) => a + s.value, 0), color: SERIES_OTHER }]
      : []),
  ];

  return (
    <div className={className}>
      <div className="flex h-3 w-full gap-[2px]" role="img" aria-label="Distribuição da carteira por ativo">
        {items.map((s, i) => (
          <div
            key={s.key}
            onPointerEnter={() => setHover(s.key)}
            onPointerLeave={() => setHover(null)}
            className={cn(
              "h-full transition-opacity",
              i === 0 && "rounded-l-[4px]",
              i === items.length - 1 && "rounded-r-[4px]",
              hover && hover !== s.key && "opacity-35",
            )}
            style={{ width: `${(s.value / total) * 100}%`, background: s.color, minWidth: 3 }}
            title={`${s.label}: ${formatPct((s.value / total) * 100, { decimals: 1 })}`}
          />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
        {items.map((s) => (
          <li
            key={s.key}
            onPointerEnter={() => setHover(s.key)}
            onPointerLeave={() => setHover(null)}
            className={cn("flex items-center gap-2 text-sm transition-opacity", hover && hover !== s.key && "opacity-50")}
          >
            <span aria-hidden className="size-2.5 shrink-0 rounded-[3px]" style={{ background: s.color }} />
            <span className="font-medium">{s.label}</span>
            <span className="num text-ink-2" title={formatBRL(s.value)}>
              {formatPct((s.value / total) * 100, { decimals: 1 })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Horizontal bar list for allocation by class or sector (comparing close values reads better than a donut). */
export function AllocationBars({ slices, className }: { slices: Slice[]; className?: string }) {
  const sorted = [...slices].sort((a, b) => b.value - a.value);
  const total = sorted.reduce((a, s) => a + s.value, 0) || 1;
  const max = sorted[0]?.value || 1;
  return (
    <ul className={cn("flex flex-col gap-3", className)}>
      {sorted.map((s) => (
        <li key={s.key} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm sm:grid-cols-[minmax(0,11rem)_1fr_7.5rem_3.5rem]">
          <span className="truncate font-medium">{s.label}</span>
          <span className="block h-2 rounded-r-[4px] bg-sunken">
            <span
              className="block h-full rounded-r-[4px]"
              style={{ width: `${(s.value / max) * 100}%`, background: "var(--series-1)" }}
            />
          </span>
          <span className="num hidden text-right text-ink-2 sm:block">{formatBRL(s.value)}</span>
          <span className="num text-right font-medium">{formatPct((s.value / total) * 100, { decimals: 1 })}</span>
        </li>
      ))}
    </ul>
  );
}
