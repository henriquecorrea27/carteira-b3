import { CheckCircle2, CircleMinus, TriangleAlert, XCircle } from "lucide-react";
import type { IndicatorStatus, IndicatorUnit } from "@/api/types";
import { InfoTip } from "@/components/ui/menu";
import { formatBRL, formatMultiple, formatNumber, formatPct, toNumber, type Numeric } from "@/lib/format";
import type { Term } from "./glossary";

export function Tip({ term, side }: { term: Term; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <InfoTip title={term.title} side={side}>
      {term.text}
    </InfoTip>
  );
}

export const STATUS: Record<IndicatorStatus, { label: string; icon: typeof CheckCircle2; className: string }> = {
  GOOD: { label: "Bom", icon: CheckCircle2, className: "text-up" },
  MID: { label: "Médio", icon: TriangleAlert, className: "text-warn" },
  BAD: { label: "Ruim", icon: XCircle, className: "text-down" },
  NA: { label: "Sem dados", icon: CircleMinus, className: "text-muted" },
};

/** Big amounts in words: 10,2 bi · 350,4 mi */
export function formatBig(value: Numeric): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1e9) return `${sign}${formatNumber(abs / 1e9, { maxDecimals: 2 })} bi`;
  if (abs >= 1e6) return `${sign}${formatNumber(abs / 1e6, { maxDecimals: 1 })} mi`;
  if (abs >= 1e3) return `${sign}${formatNumber(abs / 1e3, { maxDecimals: 1 })} mil`;
  return formatNumber(n, { maxDecimals: 0 });
}

/** −R$ 102,9 mi */
export function formatBigBRL(value: Numeric): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return `${n < 0 ? "−" : ""}R$ ${formatBig(Math.abs(n))}`;
}

/** Indicator value by unit (percentages in points). Money above R$ 1 mi goes in words. */
export function formatValue(value: Numeric, unit: IndicatorUnit, decimals = 2): string {
  const n = toNumber(value);
  if (n === null) return "—";
  switch (unit) {
    case "pct":
      return formatPct(n, { decimals });
    case "x":
      return formatMultiple(n, decimals);
    case "brl":
      return Math.abs(n) >= 1e6 ? formatBigBRL(n) : formatBRL(n);
    case "count":
      return formatNumber(n, { maxDecimals: 0 });
    default:
      return formatNumber(n, { minDecimals: decimals, maxDecimals: decimals });
  }
}
