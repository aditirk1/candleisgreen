// One chart component for every price and equity chart. It redraws when the theme changes.
import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, createChart, HistogramSeries, LineSeries, UTCTimestamp } from "lightweight-charts";
import { cssVar, useTheme } from "./theme";

export type Bar = { date: string; open?: number; high?: number; low?: number; close: number; volume?: number | null };
const RANGES: [string, number][] = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["All", 100000]];

const ts = (d: string) => Math.floor(new Date(d.length === 10 ? d + "T00:00:00Z" : d).getTime() / 1000) as UTCTimestamp;

export function PriceChart({ bars, height = 360, candles = true, label, ranges = true, defaultRange = "1Y" }:
  { bars: Bar[]; height?: number; candles?: boolean; label: string; ranges?: boolean; defaultRange?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const [range, setRange] = useState(defaultRange);
  const [style, setStyle] = useState<"candles" | "line">(candles && bars.some((b) => b.open !== undefined) ? "candles" : "line");
  const n = RANGES.find(([r]) => r === range)?.[1] ?? 252;
  const shown = useMemo(() => bars.slice(-n), [bars, n]);
  useEffect(() => {
    if (!ref.current || shown.length === 0) return;
    const chart = createChart(ref.current, {
      height, layout: { background: { color: "transparent" }, textColor: cssVar("--chart-text"), fontFamily: cssVar("--font-ui") },
      grid: { vertLines: { color: cssVar("--chart-grid") }, horzLines: { color: cssVar("--chart-grid") } },
      timeScale: { borderVisible: false }, rightPriceScale: { borderVisible: false },
    });
    if (style === "candles") {
      chart.addSeries(CandlestickSeries, { upColor: cssVar("--chart-up"), downColor: cssVar("--chart-down"), borderVisible: false,
        wickUpColor: cssVar("--chart-up"), wickDownColor: cssVar("--chart-down") })
        .setData(shown.map((b) => ({ time: ts(b.date), open: b.open ?? b.close, high: b.high ?? b.close, low: b.low ?? b.close, close: b.close })));
    } else {
      chart.addSeries(LineSeries, { color: cssVar("--chart-line"), lineWidth: 2 }).setData(shown.map((b) => ({ time: ts(b.date), value: b.close })));
    }
    if (shown.some((b) => b.volume)) {
      const vol = chart.addSeries(HistogramSeries, { color: cssVar("--chart-volume"), priceScaleId: "volume", priceFormat: { type: "volume" } });
      chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      vol.setData(shown.filter((b) => b.volume).map((b) => ({ time: ts(b.date), value: b.volume as number })));
    }
    if (shown.some((b) => b.volume)) chart.priceScale("right").applyOptions({ scaleMargins: { top: 0.06, bottom: 0.26 } });  // keep volume below price
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [shown, style, theme, height]);
  return (
    <div className="chart">
      {ranges && (
        <div className="chart-controls">
          <div className="segmented small" role="group" aria-label={`${label} range`}>
            {RANGES.map(([r]) => <button key={r} className={range === r ? "active" : ""} onClick={() => setRange(r)}>{r}</button>)}
          </div>
          {candles && bars.some((b) => b.open !== undefined) && (
            <div className="segmented small" role="group" aria-label={`${label} style`}>
              <button className={style === "candles" ? "active" : ""} onClick={() => setStyle("candles")}>Candles</button>
              <button className={style === "line" ? "active" : ""} onClick={() => setStyle("line")}>Line</button>
            </div>)}
        </div>)}
      {shown.length === 0 ? <p className="muted">No data in this range</p> : <div ref={ref} aria-label={label} />}
    </div>
  );
}
