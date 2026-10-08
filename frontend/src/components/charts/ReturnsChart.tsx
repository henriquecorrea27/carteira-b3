import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReturnPoint } from "@/api/types";
import { formatDate, formatMonthShort, formatPct } from "@/lib/format";
import { ChartTooltipBox, Legend, SERIES, axisProps, gridProps } from "./common";

const LINES = [
  { key: "portfolio", label: "Carteira", color: SERIES[0] },
  { key: "ibov", label: "Ibovespa", color: SERIES[1] },
  { key: "cdi", label: "CDI", color: SERIES[2] },
] as const;

type Row = { date: string; portfolio: number; ibov: number | null; cdi: number | null };

/** Rebases cumulative returns so the window starts at 0%. */
export function rebase(points: ReturnPoint[]): Row[] {
  if (!points.length) return [];
  const first = points[0];
  const base = (v: string | null, b: string | null) =>
    v === null || b === null ? null : ((1 + Number(v) / 100) / (1 + Number(b) / 100) - 1) * 100;
  return points.map((p) => ({
    date: p.date,
    portfolio: base(p.portfolio_pct, first.portfolio_pct) ?? 0,
    ibov: base(p.ibov_pct, first.ibov_pct),
    cdi: base(p.cdi_pct, first.cdi_pct),
  }));
}

export function ReturnsChart({ data, height = 300 }: { data: ReturnPoint[]; height?: number }) {
  const rows = rebase(data);
  const last = rows[rows.length - 1];
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-x-6 gap-y-2">
        {LINES.map((l) => (
          <li key={l.key} className="flex items-baseline gap-2">
            <span aria-hidden className="h-0.5 w-3.5 translate-y-[-3px] rounded-full" style={{ background: l.color }} />
            <span className="text-sm text-ink-2">{l.label}</span>
            <span className="num font-semibold">{last ? formatPct(last[l.key], { signed: true }) : "—"}</span>
          </li>
        ))}
      </ul>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" tickFormatter={formatMonthShort} {...axisProps} minTickGap={40} dy={6} />
            <YAxis tickFormatter={(v: number) => formatPct(v, { decimals: 0 })} {...axisProps} width={52} />
            <ReferenceLine y={0} stroke="var(--axis)" />
            <Tooltip
              cursor={{ stroke: "var(--line-strong)", strokeWidth: 1 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as Row;
                return (
                  <ChartTooltipBox
                    title={formatDate(row.date)}
                    rows={LINES.map((l) => ({ key: l.key, label: l.label, value: formatPct(row[l.key], { signed: true }), color: l.color }))}
                  />
                );
              }}
            />
            {LINES.map((l) => (
              <Line
                key={l.key}
                dataKey={l.key}
                type="monotone"
                stroke={l.color}
                strokeWidth={2}
                dot={false}
                connectNulls
                activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Legend className="sr-only" items={LINES.map((l) => ({ label: l.label, color: l.color }))} />
    </div>
  );
}
