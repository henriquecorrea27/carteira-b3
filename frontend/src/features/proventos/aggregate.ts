import type { Dividend } from "@/api/types";
import type { MonthBar } from "@/components/charts/DividendBars";

/** Month of a dividend for charts: payment month, or data-com month when the payment date is unknown. */
export function monthOf(d: Dividend): string {
  return (d.pay_date ?? d.ex_date).slice(0, 7);
}

export const isReceived = (d: Dividend) => d.status !== "ANNOUNCED";

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const idx = y * 12 + (m - 1) + delta;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

/** Last `months` months up to the current one, plus future months that already have announced payments. */
export function monthlyBars(dividends: Dividend[], today: string, months = 12): MonthBar[] {
  const current = today.slice(0, 7);
  const first = shiftMonth(current, -(months - 1));
  const futureMonths = dividends.filter((d) => !isReceived(d) && monthOf(d) > current).map(monthOf);
  const last = futureMonths.length ? futureMonths.sort().at(-1)! : current;
  const bars: MonthBar[] = [];
  for (let m = first; m <= last; m = shiftMonth(m, 1)) bars.push({ month: m, received: 0, receivable: 0 });
  const index = new Map(bars.map((b) => [b.month, b]));
  for (const d of dividends) {
    const bar = index.get(monthOf(d));
    if (!bar) continue;
    if (isReceived(d)) bar.received += Number(d.net);
    else bar.receivable += Number(d.net);
  }
  return bars;
}

export interface YearRow {
  year: number;
  months: number[];
  total: number;
  average: number;
}

/** Received (net) per year × month, most recent year first. Average divides by months elapsed. */
export function yearMonthTable(dividends: Dividend[], today: string): YearRow[] {
  const byYear = new Map<number, number[]>();
  for (const d of dividends) {
    if (!isReceived(d)) continue;
    const [y, m] = monthOf(d).split("-").map(Number);
    if (!byYear.has(y)) byYear.set(y, Array(12).fill(0));
    byYear.get(y)![m - 1] += Number(d.net);
  }
  const currentYear = Number(today.slice(0, 4));
  const currentMonth = Number(today.slice(5, 7));
  return [...byYear.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, months]) => {
      const total = months.reduce((a, v) => a + v, 0);
      const elapsed = year === currentYear ? currentMonth : 12;
      return { year, months, total, average: total / elapsed };
    });
}

/** Net received per asset inside a window [from, to]. */
export function byAsset(dividends: Dividend[], from: string, to: string): { ticker: string; total: number }[] {
  const totals = new Map<string, number>();
  for (const d of dividends) {
    const date = d.pay_date ?? d.ex_date;
    if (!isReceived(d) || date < from || date > to) continue;
    totals.set(d.ticker, (totals.get(d.ticker) ?? 0) + Number(d.net));
  }
  return [...totals.entries()].map(([ticker, total]) => ({ ticker, total })).sort((a, b) => b.total - a.total);
}

export interface AgendaItem {
  date: string;
  kind: "PAYMENT" | "EX_DATE";
  dividend: Dividend;
}

/** Upcoming payments and data-com dates, chronological. */
export function agenda(dividends: Dividend[], today: string): AgendaItem[] {
  const items: AgendaItem[] = [];
  for (const d of dividends) {
    if (d.ex_date >= today) items.push({ date: d.ex_date, kind: "EX_DATE", dividend: d });
    if (d.pay_date && d.pay_date >= today && d.status === "ANNOUNCED") items.push({ date: d.pay_date, kind: "PAYMENT", dividend: d });
    if (!d.pay_date && d.status === "ANNOUNCED" && d.ex_date < today) items.push({ date: d.ex_date, kind: "PAYMENT", dividend: d });
  }
  return items.sort((a, b) => a.date.localeCompare(b.date) || a.kind.localeCompare(b.kind));
}
