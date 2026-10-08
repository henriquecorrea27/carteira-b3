/**
 * pt-BR formatters. The backend sends money and quantities as decimal strings;
 * they are parsed to numbers only here, for display.
 */

export type Numeric = string | number | null | undefined;

export function toNumber(value: Numeric): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

const DASH = "—";
const MINUS = "−";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const brlPrecise = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

function clean(text: string): string {
  return text.replace(/ /g, " ");
}

/** R$ 1.234,56 */
export function formatBRL(value: Numeric, opts: { precise?: boolean; signed?: boolean } = {}): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = clean((opts.precise ? brlPrecise : brl).format(Math.abs(n)));
  if (n < 0 && text !== "R$ 0,00") return `${MINUS}${text}`;
  if (opts.signed && n > 0) return `+${text}`;
  return text;
}

/** Compact money for chart axes: R$ 12 mil, R$ 1,2 mi */
export function formatBRLCompact(value: Numeric): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const abs = Math.abs(n);
  const sign = n < 0 ? MINUS : "";
  if (abs >= 1_000_000) return `${sign}R$ ${formatNumber(abs / 1_000_000, { maxDecimals: 1 })} mi`;
  if (abs >= 1_000) return `${sign}R$ ${formatNumber(abs / 1_000, { maxDecimals: 1 })} mil`;
  return `${sign}R$ ${formatNumber(abs, { maxDecimals: 0 })}`;
}

/** 1.234,5 — trailing zeros dropped beyond minDecimals */
export function formatNumber(
  value: Numeric,
  opts: { minDecimals?: number; maxDecimals?: number } = {},
): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: opts.minDecimals ?? 0,
    maximumFractionDigits: opts.maxDecimals ?? 2,
  }).format(Math.abs(n));
  return n < 0 && /[1-9]/.test(text) ? `${MINUS}${text}` : text;
}

/** Share quantities: integers plain, fractions (bonificações) up to 2 decimals. */
export function formatQuantity(value: Numeric): string {
  return formatNumber(value, { maxDecimals: 2 });
}

/**
 * Percentages. Input is in percentage points ("14.7" → "14,70%").
 * `signed` prefixes + on positive values.
 */
export function formatPct(value: Numeric, opts: { decimals?: number; signed?: boolean } = {}): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const d = opts.decimals ?? 2;
  const text = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(Math.abs(n));
  const isZero = !/[1-9]/.test(text);
  if (n < 0 && !isZero) return `${MINUS}${text}%`;
  if (opts.signed && n > 0 && !isZero) return `+${text}%`;
  return `${text}%`;
}

/** Multiples like P/L: 8,4x */
export function formatMultiple(value: Numeric, decimals = 1): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return `${formatNumber(n, { minDecimals: decimals, maxDecimals: decimals })}x`;
}

export const MONTH_LABELS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "2026-10-08" → "08/10/2026" (no timezone conversion). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return DASH;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

/** "2026-10-08" → "08/10" */
export function formatDayMonth(iso: string | null | undefined): string {
  const full = formatDate(iso);
  return full === DASH ? full : full.slice(0, 5);
}

/** "2026-10" or "2026-10-08" → "out/26" */
export function formatMonthShort(iso: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(iso);
  if (!match) return DASH;
  return `${MONTH_LABELS[Number(match[2]) - 1]}/${match[1].slice(2)}`;
}

/** "2026-10" → "outubro de 2026" */
export function formatMonthLong(iso: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(iso);
  if (!match) return DASH;
  const name = new Intl.DateTimeFormat("pt-BR", { month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)),
  );
  return `${name} de ${match[1]}`;
}

/** "2026-10-08T18:05:00-03:00" → "08/10 18:05" */
export function formatDateTimeShort(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  if (!match) return formatDate(iso);
  return `${match[3]}/${match[2]} ${match[4]}:${match[5]}`;
}

/** Sign of a numeric value: 1, -1 or 0 (null → 0). */
export function signOf(value: Numeric): -1 | 0 | 1 {
  const n = toNumber(value);
  if (n === null || n === 0) return 0;
  return n > 0 ? 1 : -1;
}

/** Parses user input in pt-BR ("1.234,56" or "1234.56") to a decimal string, or null. */
export function parseDecimalInput(input: string): string | null {
  const s = input.trim().replace(/\s/g, "").replace(/^R\$/, "");
  if (!s) return null;
  let normalized: string;
  if (s.includes(",")) normalized = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) normalized = s.replace(/\./g, "");
  else normalized = s;
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  return normalized;
}
