import * as React from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Logical,
  type MouseEventParams,
  type SeriesType,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PriceBar } from "@/api/types";
import { useCssVars } from "@/app/theme";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const VARS = ["--surface", "--ink", "--ink-2", "--muted", "--grid", "--line-strong", "--series-1", "--series-2", "--up", "--down"] as const;
const RIGHT_OFFSET = 6; // empty bars after the last one, like TradingView

function toTime(iso: string): UTCTimestamp {
  return (Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp;
}

function hexAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const price = (n: number) => formatNumber(n, { minDecimals: 2, maxDecimals: 2 });
const signed = (n: number, text: string) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${text}`;
const pct = (n: number) => signed(n, `${formatNumber(Math.abs(n) * 100, { minDecimals: 2, maxDecimals: 2 })}%`);

function volume(n: number): string {
  if (n >= 1e9) return `${formatNumber(n / 1e9, { maxDecimals: 2 })} bi`;
  if (n >= 1e6) return `${formatNumber(n / 1e6, { maxDecimals: 2 })} mi`;
  if (n >= 1e3) return `${formatNumber(n / 1e3, { maxDecimals: 1 })} mil`;
  return formatNumber(n, { maxDecimals: 0 });
}

export interface LinePoint {
  time: string;
  value: number;
}

interface Point {
  logical: number;
  price: number;
}

interface Measure {
  a: Point;
  b: Point;
  fixed: boolean;
}

/** Calendar days between two ISO dates. */
function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
}

/**
 * TradingView-like price chart (lightweight-charts): candles or line, volume, OHLC legend, the SMA overlay,
 * free zoom/scroll and a ruler (button or Shift + click) that measures the change between two points.
 */
export function PriceChart({
  bars,
  mode,
  overlay,
  overlayLabel,
  visibleBars,
  ruler,
  onRulerChange,
  height = 420,
}: {
  bars: PriceBar[];
  mode: "area" | "candles";
  overlay?: LinePoint[];
  overlayLabel?: string;
  /** Bars shown when the range changes (null = everything); the user can zoom and scroll from there. */
  visibleBars: number | null;
  /** Ruler armed: the next click starts a measurement. */
  ruler: boolean;
  onRulerChange: (on: boolean) => void;
  height?: number;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<ISeriesApi<SeriesType> | null>(null);
  const c = useCssVars(VARS);
  const [hover, setHover] = React.useState<number | null>(null); // bar index under the cursor
  const [measure, setMeasure] = React.useState<Measure | null>(null);
  const [, setTick] = React.useState(0); // redraw the ruler when the chart scrolls or zooms

  // Handlers subscribed once per chart read the latest values from refs
  const live = React.useRef({ ruler, measure, onRulerChange, visibleBars });
  live.current = { ruler, measure, onRulerChange, visibleBars };

  const smaByTime = React.useMemo(() => new Map((overlay ?? []).map((p) => [p.time, p.value])), [overlay]);

  const applyRange = React.useCallback(() => {
    const chart = chartRef.current;
    if (!chart || bars.length === 0) return;
    const n = live.current.visibleBars;
    const last = bars.length - 1;
    chart.timeScale().setVisibleLogicalRange({
      from: (n === null ? 0 : Math.max(0, last - n + 1)) as Logical,
      to: (last + RIGHT_OFFSET) as Logical,
    });
  }, [bars]);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: c["--surface"] },
        textColor: c["--muted"],
        fontFamily: "Instrument Sans Variable, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      localization: { locale: "pt-BR", priceFormatter: price },
      grid: { vertLines: { color: hexAlpha(c["--grid"], 0.6) }, horzLines: { color: c["--grid"] } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.2 } },
      timeScale: { borderVisible: false, fixLeftEdge: true, rightOffset: RIGHT_OFFSET },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: c["--muted"], style: LineStyle.Dashed, width: 1, labelBackgroundColor: c["--ink-2"] },
        horzLine: { color: c["--muted"], style: LineStyle.Dashed, width: 1, labelBackgroundColor: c["--ink-2"] },
      },
    });
    chartRef.current = chart;

    // Volume at the bottom, on its own scale
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: "volume", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    vol.setData(
      bars.map((b) => ({
        time: toTime(b.time),
        value: Number(b.volume),
        color: hexAlpha(Number(b.close) >= Number(b.open) ? c["--up"] : c["--down"], 0.3),
      })),
    );

    let series: ISeriesApi<SeriesType>;
    if (mode === "area") {
      series = chart.addSeries(AreaSeries, {
        lineColor: c["--series-1"],
        lineWidth: 2,
        topColor: hexAlpha(c["--series-1"], 0.16),
        bottomColor: hexAlpha(c["--series-1"], 0.01),
        priceLineStyle: LineStyle.Dotted,
      });
      series.setData(bars.map((b) => ({ time: toTime(b.time), value: Number(b.close) })));
    } else {
      series = chart.addSeries(CandlestickSeries, {
        upColor: c["--up"],
        downColor: c["--down"],
        borderVisible: false,
        wickUpColor: c["--up"],
        wickDownColor: c["--down"],
        priceLineStyle: LineStyle.Dotted,
      });
      series.setData(
        bars.map((b) => ({ time: toTime(b.time), open: Number(b.open), high: Number(b.high), low: Number(b.low), close: Number(b.close) })),
      );
    }
    seriesRef.current = series;

    if (overlay?.length) {
      const line = chart.addSeries(LineSeries, {
        color: c["--series-2"],
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
      });
      line.setData(overlay.map((p) => ({ time: toTime(p.time), value: p.value })));
    }

    const pointOf = (param: MouseEventParams): Point | null => {
      if (!param.point || param.logical === undefined) return null;
      const p = series.coordinateToPrice(param.point.y);
      if (p === null) return null;
      return { logical: Math.max(0, Math.min(bars.length - 1, Math.round(param.logical))), price: p };
    };

    const onMove = (param: MouseEventParams) => {
      const i = param.logical === undefined || !param.point ? null : Math.round(param.logical);
      setHover(i !== null && i >= 0 && i < bars.length ? i : null);
      const m = live.current.measure;
      if (m && !m.fixed) {
        const p = pointOf(param);
        if (p) setMeasure({ ...m, b: p });
      }
    };

    // Native clicks: the chart's own click event swallows a quick second click as a double click
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onClick = (e: MouseEvent) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return; // a drag that scrolled the chart
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const logical = chart.timeScale().coordinateToLogical(x);
      const value = x <= chart.paneSize().width ? series.coordinateToPrice(y) : null;
      const p = logical === null || value === null ? null : { logical: Math.max(0, Math.min(bars.length - 1, Math.round(logical))), price: value };
      const { ruler: armed, measure: m, onRulerChange: setArmed } = live.current;
      if (m && !m.fixed) {
        setMeasure(p ? { ...m, b: p, fixed: true } : { ...m, fixed: true });
        setArmed(false);
      } else if (p && (armed || e.shiftKey)) {
        setMeasure({ a: p, b: p, fixed: false });
      } else if (m) {
        setMeasure(null);
      }
    };

    const onRange = () => setTick((t) => t + 1);
    chart.subscribeCrosshairMove(onMove);
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("click", onClick);
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    applyRange();
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("click", onClick);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [bars, mode, overlay, c, applyRange]);

  // Range presets (6M, 1A…) move the view without rebuilding the chart
  React.useEffect(applyRange, [visibleBars, applyRange]);

  // A new data set or chart type drops the measurement
  React.useEffect(() => setMeasure(null), [bars, mode]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMeasure(null);
        live.current.onRulerChange(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const i = hover ?? bars.length - 1;
  const bar = bars[i];

  return (
    <div className={cn("relative w-full select-none", ruler && "cursor-crosshair")} style={{ height }}>
      <div ref={ref} className="absolute inset-0" />
      {bar && <OhlcLegend bar={bar} prev={bars[i - 1]} sma={smaByTime.get(bar.time)} smaLabel={overlayLabel} colors={c} />}
      {measure && chartRef.current && seriesRef.current && (
        <RulerOverlay measure={measure} bars={bars} chart={chartRef.current} series={seriesRef.current} colors={c} />
      )}
      {ruler && !measure && (
        <div className="pointer-events-none absolute bottom-12 left-1/2 -translate-x-1/2 rounded-md bg-ink/85 px-2.5 py-1 text-xs text-paper">
          Clique no ponto inicial e depois no final · Esc cancela
        </div>
      )}
    </div>
  );
}

/** Top-left legend like TradingView: open, high, low, close and the change of the bar under the cursor. */
function OhlcLegend({
  bar,
  prev,
  sma,
  smaLabel,
  colors,
}: {
  bar: PriceBar;
  prev?: PriceBar;
  sma?: number;
  smaLabel?: string;
  colors: Record<(typeof VARS)[number], string>;
}) {
  const [o, h, l, cl] = [bar.open, bar.high, bar.low, bar.close].map(Number);
  const base = prev ? Number(prev.close) : o;
  const change = cl - base;
  const tone = { color: change >= 0 ? colors["--up"] : colors["--down"] };
  const [y, m, d] = bar.time.split("-");
  return (
    <div className="pointer-events-none absolute left-2 top-1.5 z-[2] flex max-w-[calc(100%-5rem)] flex-col gap-0.5 rounded bg-surface/80 px-1.5 py-1 text-xs leading-tight backdrop-blur-[1px]">
      <div className="num flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 text-ink-2">
        <span className="text-muted">
          {d}/{m}/{y}
        </span>
        <span>
          A <b style={tone} className="font-medium">{price(o)}</b>
        </span>
        <span>
          Máx <b style={tone} className="font-medium">{price(h)}</b>
        </span>
        <span>
          Mín <b style={tone} className="font-medium">{price(l)}</b>
        </span>
        <span>
          F <b style={tone} className="font-medium">{price(cl)}</b>
        </span>
        <b style={tone} className="font-medium">
          {signed(change, price(Math.abs(change)))} ({pct(base ? change / base : 0)})
        </b>
      </div>
      <div className="num flex flex-wrap gap-x-2.5 text-ink-2">
        {sma !== undefined && (
          <span>
            {smaLabel ?? "Média"} <b style={{ color: colors["--series-2"] }} className="font-medium">{price(sma)}</b>
          </span>
        )}
        <span>
          Vol <b className="font-medium text-ink">{volume(Number(bar.volume))}</b>
        </span>
      </div>
    </div>
  );
}

/** The measurement box: price change (R$ and %), trading sessions and calendar days between two points. */
function RulerOverlay({
  measure,
  bars,
  chart,
  series,
  colors,
}: {
  measure: Measure;
  bars: PriceBar[];
  chart: IChartApi;
  series: ISeriesApi<SeriesType>;
  colors: Record<(typeof VARS)[number], string>;
}) {
  const ts = chart.timeScale();
  const x1 = ts.logicalToCoordinate(measure.a.logical as Logical);
  const x2 = ts.logicalToCoordinate(measure.b.logical as Logical);
  const y1 = series.priceToCoordinate(measure.a.price);
  const y2 = series.priceToCoordinate(measure.b.price);
  if (x1 === null || x2 === null || y1 === null || y2 === null) return null;

  const diff = measure.b.price - measure.a.price;
  const up = diff >= 0;
  const color = up ? colors["--up"] : colors["--down"];
  const sessions = measure.b.logical - measure.a.logical;
  const from = bars[Math.min(measure.a.logical, measure.b.logical)]?.time;
  const to = bars[Math.max(measure.a.logical, measure.b.logical)]?.time;
  const days = from && to ? daysBetween(from, to) : 0;

  const left = Math.min(x1, x2);
  const top = Math.min(y1, y2);
  const w = Math.max(1, Math.abs(x2 - x1));
  const h = Math.max(1, Math.abs(y2 - y1));
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const id = up ? "ruler-up" : "ruler-down";

  return (
    <>
      <svg className="pointer-events-none absolute inset-0 z-[1] h-full w-full overflow-visible" aria-hidden>
        <defs>
          <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={color} />
          </marker>
        </defs>
        <rect x={left} y={top} width={w} height={h} fill={hexAlpha(color, 0.14)} />
        <line x1={midX} y1={y1} x2={midX} y2={y2} stroke={color} strokeWidth={1.5} markerEnd={h > 12 ? `url(#${id})` : undefined} />
        <line x1={x1} y1={midY} x2={x2} y2={midY} stroke={color} strokeWidth={1.5} markerEnd={w > 12 ? `url(#${id})` : undefined} />
      </svg>
      <div
        role="status"
        className="num pointer-events-none absolute z-[3] -translate-x-1/2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-center text-xs font-medium leading-snug text-white shadow-md"
        style={{
          left: Math.max(70, Math.min(midX, (chart.paneSize().width || 0) - 70)),
          top: up ? Math.max(4, top - 46) : top + h + 6,
          background: color,
        }}
      >
        <div>
          {signed(diff, `R$ ${price(Math.abs(diff))}`)} ({pct(measure.a.price ? diff / measure.a.price : 0)})
        </div>
        <div className="opacity-90">
          {Math.abs(sessions)} {Math.abs(sessions) === 1 ? "pregão" : "pregões"} · {days} {days === 1 ? "dia" : "dias"}
        </div>
      </div>
    </>
  );
}
