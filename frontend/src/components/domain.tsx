/** Small, reusable pieces of the portfolio vocabulary. */
import { ArrowDownRight, ArrowUpRight, Ban, Check, Clock3, Minus } from "lucide-react";
import type { AssetClass, Decision, DividendStatus, Source } from "@/api/types";
import { formatBRL, formatPct, signOf, type Numeric } from "@/lib/format";
import { DECISION_LABEL, DIVIDEND_STATUS_LABEL, SOURCE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";

const decisionStyle: Record<Decision, { tone: "up" | "warn" | "down"; icon: typeof Check }> = {
  BUY: { tone: "up", icon: Check },
  WAIT: { tone: "warn", icon: Clock3 },
  AVOID: { tone: "down", icon: Ban },
};

/** Rule-engine decision — always icon + label, never color alone. */
export function DecisionBadge({ decision, className }: { decision: Decision; className?: string }) {
  const s = decisionStyle[decision];
  const Icon = s.icon;
  return (
    <Badge tone={s.tone} className={cn("font-semibold", className)}>
      <Icon className="stroke-[2.5]" />
      {DECISION_LABEL[decision]}
    </Badge>
  );
}

function scoreColor(score: number) {
  if (score >= 70) return "var(--up)";
  if (score >= 50) return "var(--warn)";
  return "var(--down)";
}

/** 0–100 score as a figure plus a thin meter. */
export function ScoreMeter({
  score,
  inconclusive,
  size = "sm",
  className,
}: {
  score: number | null;
  inconclusive?: boolean;
  size?: "sm" | "lg";
  className?: string;
}) {
  if (score === null) return <span className="text-muted">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-2", className)} title={inconclusive ? "Nota inconclusiva: mais de 30% do peso sem dados" : undefined}>
      <span className={cn("num font-semibold", size === "lg" ? "text-xl" : "text-base", inconclusive && "text-muted")}>
        {score}
        {inconclusive && <span className="align-super text-2xs">*</span>}
      </span>
      <span className={cn("relative overflow-hidden rounded-full bg-sunken", size === "lg" ? "h-1.5 w-20" : "h-1 w-10")} aria-hidden>
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${Math.max(3, score)}%`, background: inconclusive ? "var(--muted)" : scoreColor(score) }}
        />
      </span>
    </span>
  );
}

/** Signed money or percentage colored by direction, with an arrow so it survives without color. */
export function Delta({
  value,
  kind = "pct",
  decimals = 2,
  arrow = true,
  className,
}: {
  value: Numeric;
  kind?: "pct" | "brl";
  decimals?: number;
  arrow?: boolean;
  className?: string;
}) {
  const sign = signOf(value);
  const Icon = sign > 0 ? ArrowUpRight : sign < 0 ? ArrowDownRight : Minus;
  const text = kind === "pct" ? formatPct(value, { decimals, signed: true }) : formatBRL(value, { signed: true });
  return (
    <span
      className={cn(
        "num inline-flex items-center gap-0.5 whitespace-nowrap",
        sign > 0 && "text-up",
        sign < 0 && "text-down",
        sign === 0 && "text-ink-2",
        className,
      )}
    >
      {arrow && <Icon className="size-3.5 shrink-0 stroke-[2.25]" aria-hidden />}
      {text}
    </span>
  );
}

export function SourceBadge({ source, edited }: { source: Source; edited?: boolean }) {
  return (
    <Badge tone={source === "AUTO" ? "info" : source === "B3" ? "outline" : "neutral"}>
      {SOURCE_LABEL[source]}
      {edited && <span className="font-normal opacity-75">· editado</span>}
    </Badge>
  );
}

export function DividendStatusBadge({ status }: { status: DividendStatus }) {
  const tone = status === "ANNOUNCED" ? "info" : status === "CONFIRMED" ? "up" : "neutral";
  return <Badge tone={tone}>{DIVIDEND_STATUS_LABEL[status]}</Badge>;
}

const classMark: Record<AssetClass, string> = {
  STOCK: "bg-sunken text-ink",
  FII: "bg-info-soft text-info",
  ETF: "bg-up-soft text-up",
  BDR: "bg-warn-soft text-warn",
};

/** Ticker monogram — no third-party logos; class is hinted by tone. */
export function AssetMark({ ticker, assetClass, className }: { ticker: string; assetClass: AssetClass; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "condensed inline-flex size-8 shrink-0 items-center justify-center rounded-md text-2xs font-bold tracking-tight ring-1 ring-inset ring-line",
        classMark[assetClass],
        className,
      )}
    >
      {ticker.slice(0, 4)}
    </span>
  );
}

export function AssetCell({
  ticker,
  name,
  assetClass,
  extra,
}: {
  ticker: string;
  name: string;
  assetClass: AssetClass;
  extra?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <AssetMark ticker={ticker} assetClass={assetClass} />
      <div className="min-w-0 leading-tight">
        <div className="flex items-center gap-1.5 font-semibold">
          {ticker}
          {extra}
        </div>
        <div className="max-w-[14rem] truncate text-sm text-ink-2" title={name}>
          {name}
        </div>
      </div>
    </div>
  );
}
