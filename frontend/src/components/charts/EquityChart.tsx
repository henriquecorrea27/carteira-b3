import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/api/types";
import { formatBRL, formatBRLCompact, formatDate, formatMonthShort } from "@/lib/format";
import { ChartTooltipBox, Legend, axisProps, gridProps } from "./common";

interface Row {
  date: string;
  equity: number;
  invested: number;
}

const EQUITY = "var(--series-1)";
const INVESTED = "var(--series-neutral)";

/** Patrimônio (line + wash) against valor aplicado (stepped reference line). */
export function EquityChart({ data, height = 280 }: { data: EquityPoint[]; height?: number }) {
  const rows: Row[] = data.map((p) => ({ date: p.date, equity: Number(p.equity), invested: Number(p.invested) }));
  const monthTicks = rows
    .filter((r, i) => i === 0 || r.date.slice(0, 7) !== rows[i - 1].date.slice(0, 7))
    .map((r) => r.date);
  const step = Math.max(1, Math.ceil(monthTicks.length / 8));
  const ticks = monthTicks.filter((_, i) => i % step === 0);

  return (
    <div>
      <Legend
        className="mb-3"
        items={[
          { label: "Patrimônio", color: EQUITY },
          { label: "Valor aplicado", color: INVESTED },
        ]}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="equityWash" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={EQUITY} stopOpacity={0.14} />
                <stop offset="100%" stopColor={EQUITY} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" ticks={ticks} tickFormatter={formatMonthShort} {...axisProps} minTickGap={24} dy={6} />
            <YAxis tickFormatter={formatBRLCompact} {...axisProps} width={78} domain={["auto", "auto"]} />
            <Tooltip
              cursor={{ stroke: "var(--line-strong)", strokeWidth: 1 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as Row;
                const gain = row.equity - row.invested;
                return (
                  <ChartTooltipBox
                    title={formatDate(row.date)}
                    rows={[
                      { key: "e", label: "Patrimônio", value: formatBRL(row.equity), color: EQUITY },
                      { key: "i", label: "Valor aplicado", value: formatBRL(row.invested), color: INVESTED },
                    ]}
                    footer={
                      <>
                        Resultado <span className={gain >= 0 ? "num font-medium text-up" : "num font-medium text-down"}>{formatBRL(gain, { signed: true })}</span>
                      </>
                    }
                  />
                );
              }}
            />
            <Area type="monotone" dataKey="equity" stroke={EQUITY} strokeWidth={2} fill="url(#equityWash)" activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="invested" stroke={INVESTED} strokeWidth={1.5} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
