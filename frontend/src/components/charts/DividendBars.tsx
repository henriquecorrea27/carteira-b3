import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatBRL, formatBRLCompact, formatMonthLong, formatMonthShort } from "@/lib/format";
import { ChartTooltipBox, Legend, axisProps, gridProps } from "./common";

export interface MonthBar {
  month: string; // YYYY-MM
  received: number;
  receivable: number;
}

const RECEIVED = "var(--series-1)";
const RECEIVABLE = "var(--series-3)";

/** Monthly dividends: received and still-to-receive, stacked with a 2px surface gap. */
export function DividendBars({
  data,
  height = 260,
  onSelectMonth,
  selected,
}: {
  data: MonthBar[];
  height?: number;
  onSelectMonth?: (month: string) => void;
  selected?: string | null;
}) {
  const hasReceivable = data.some((d) => d.receivable > 0);
  return (
    <div>
      <Legend
        className="mb-3"
        items={[
          { label: "Recebidos", color: RECEIVED, shape: "bar" },
          ...(hasReceivable ? [{ label: "A receber", color: RECEIVABLE, shape: "bar" as const }] : []),
        ]}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
            barCategoryGap="22%"
            onClick={(state) => {
              const label = (state as { activeLabel?: string } | null)?.activeLabel;
              if (label && onSelectMonth) onSelectMonth(label);
            }}
          >
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="month" tickFormatter={formatMonthShort} {...axisProps} interval="preserveStartEnd" minTickGap={8} dy={6} />
            <YAxis tickFormatter={formatBRLCompact} {...axisProps} width={68} />
            <Tooltip
              cursor={{ fill: "var(--sunken)", opacity: 0.7 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as MonthBar;
                return (
                  <ChartTooltipBox
                    title={formatMonthLong(row.month)}
                    rows={[
                      { key: "r", label: "Recebidos", value: formatBRL(row.received), color: RECEIVED, shape: "bar" },
                      ...(row.receivable > 0
                        ? [{ key: "a", label: "A receber", value: formatBRL(row.receivable), color: RECEIVABLE, shape: "bar" as const }]
                        : []),
                    ]}
                  />
                );
              }}
            />
            <Bar
              dataKey="received"
              stackId="m"
              fill={RECEIVED}
              maxBarSize={24}
              stroke="var(--surface)"
              strokeWidth={2}
              radius={[0, 0, 0, 0]}
              isAnimationActive={false}
              cursor={onSelectMonth ? "pointer" : undefined}
              shape={(props: unknown) => <RoundedTop {...(props as BarShapeProps)} topKey="receivable" selected={selected} />}
            />
            <Bar
              dataKey="receivable"
              stackId="m"
              fill={RECEIVABLE}
              maxBarSize={24}
              stroke="var(--surface)"
              strokeWidth={2}
              isAnimationActive={false}
              cursor={onSelectMonth ? "pointer" : undefined}
              shape={(props: unknown) => <RoundedTop {...(props as BarShapeProps)} isTop selected={selected} />}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface BarShapeProps {
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  payload: MonthBar;
}

/** 4px rounded data-end, square at the baseline; the top segment of the stack gets the rounding. */
function RoundedTop({
  x,
  y,
  width,
  height,
  fill,
  payload,
  isTop,
  topKey,
  selected,
}: BarShapeProps & { isTop?: boolean; topKey?: keyof MonthBar; selected?: string | null }) {
  if (!height || height <= 0) return null;
  const rounded = isTop || (topKey ? !(Number(payload[topKey]) > 0) : false);
  const r = rounded ? Math.min(4, width / 2, height) : 0;
  const dim = selected && payload.month !== selected ? 0.35 : 1;
  // Leave a 2px surface gap between stacked segments.
  const h = isTop ? Math.max(0, height - 2) : height;
  const top = y;
  const path = r
    ? `M${x},${top + h} L${x},${top + r} Q${x},${top} ${x + r},${top} L${x + width - r},${top} Q${x + width},${top} ${x + width},${top + r} L${x + width},${top + h} Z`
    : `M${x},${top} h${width} v${h} h${-width} Z`;
  return <path d={path} fill={fill} opacity={dim} />;
}
