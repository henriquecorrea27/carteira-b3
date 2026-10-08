import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const SERIES = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
] as const;

export const SERIES_OTHER = "var(--series-other)";

export const axisProps = {
  stroke: "var(--axis)",
  tick: { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-sans)" },
  tickLine: false,
  axisLine: false,
} as const;

export const gridProps = {
  stroke: "var(--grid)",
  strokeWidth: 1,
  vertical: false,
} as const;

export interface TooltipRow {
  key: string;
  label: string;
  value: string;
  color: string;
  shape?: "line" | "bar";
}

/** Tooltip body: value first (strong), series name second, keyed by a short stroke. */
export function ChartTooltipBox({ title, rows, footer }: { title: ReactNode; rows: TooltipRow[]; footer?: ReactNode }) {
  return (
    <div className="min-w-44 rounded-md border border-line bg-surface px-3 py-2 shadow-[0_12px_32px_-12px_rgb(0_0_0/0.35)]">
      <div className="mb-1.5 text-sm text-ink-2">{title}</div>
      <ul className="flex flex-col gap-1">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-2">
            <span
              aria-hidden
              className={cn("shrink-0 rounded-full", r.shape === "bar" ? "h-2.5 w-2.5 rounded-[3px]" : "h-0.5 w-3")}
              style={{ background: r.color }}
            />
            <span className="num font-semibold">{r.value}</span>
            <span className="text-sm text-ink-2">{r.label}</span>
          </li>
        ))}
      </ul>
      {footer && <div className="mt-1.5 border-t border-line pt-1.5 text-sm text-ink-2">{footer}</div>}
    </div>
  );
}

export function Legend({ items, className }: { items: { label: string; color: string; shape?: "line" | "bar" }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2", className)}>
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className={i.shape === "bar" ? "size-2.5 rounded-[3px]" : "h-0.5 w-3.5 rounded-full"}
            style={{ background: i.color }}
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
