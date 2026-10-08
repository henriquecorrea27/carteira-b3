import * as React from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PriceBar } from "@/api/types";
import { useCssVars } from "@/app/theme";

const VARS = ["--surface", "--ink-2", "--muted", "--grid", "--line-strong", "--series-1", "--up", "--down"] as const;

function toTime(iso: string): UTCTimestamp {
  return (Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp;
}

function hexAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Price history on TradingView lightweight-charts (base for the F8 chart analysis). */
export function PriceChart({ bars, mode, height = 320 }: { bars: PriceBar[]; mode: "area" | "candles"; height?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const c = useCssVars(VARS);

  React.useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: c["--surface"] },
        textColor: c["--muted"],
        fontFamily: "Instrument Sans Variable, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      localization: {
        locale: "pt-BR",
        priceFormatter: (p: number) => p.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c["--grid"] } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: c["--line-strong"], style: LineStyle.Solid, width: 1, labelBackgroundColor: c["--ink-2"] },
        horzLine: { color: c["--line-strong"], style: LineStyle.Solid, width: 1, labelBackgroundColor: c["--ink-2"] },
      },
    });
    chartRef.current = chart;

    if (mode === "area") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: c["--series-1"],
        lineWidth: 2,
        topColor: hexAlpha(c["--series-1"], 0.16),
        bottomColor: hexAlpha(c["--series-1"], 0.01),
        priceLineVisible: false,
      });
      series.setData(bars.map((b) => ({ time: toTime(b.time), value: Number(b.close) })));
    } else {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: c["--up"],
        downColor: c["--down"],
        borderVisible: false,
        wickUpColor: c["--up"],
        wickDownColor: c["--down"],
        priceLineVisible: false,
      });
      series.setData(
        bars.map((b) => ({ time: toTime(b.time), open: Number(b.open), high: Number(b.high), low: Number(b.low), close: Number(b.close) })),
      );
    }
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, mode, height, c]);

  return <div ref={ref} style={{ height }} className="w-full" />;
}
