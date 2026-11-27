import { useEffect, useRef, useState } from "react";
import { createChart, LineSeries, UTCTimestamp } from "lightweight-charts";
import { getJSON } from "../api";
import { pct, signed, timeET, sideLabel } from "../format";

type NewsRow = { cluster_id: string; headline: string; first_usable_at: string; category: { label: string } | null };
type Stock = {
  symbol: string; status: string; reason?: string; name: string; type: string; type_inferred: boolean;
  industry: { code: string; plain: string };
  price: { last: number | null; date: string | null; source: string | null; change: Record<string, number | null>; volatility_annual: number | null };
  history: { date: string; close: number }[]; system_view: string; signal: number | null; composite_score: number | null;
  proposal: { session_date: string; side: string; quantity: number; status: string } | null;
  can_trade: boolean; tag_note: string; news?: NewsRow[];
};

function Chart({ points }: { points: Stock["history"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    const css = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, { height: 180, layout: { background: { color: "transparent" }, textColor: css.getPropertyValue("--muted").trim() },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } }, timeScale: { borderVisible: false }, rightPriceScale: { borderVisible: false } });
    chart.addSeries(LineSeries, { color: css.getPropertyValue("--accent").trim(), lineWidth: 2 })
      .setData(points.map((p) => ({ time: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp, value: p.close })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  return <div ref={ref} aria-label="Stock price chart" />;
}

export function StockPanel({ symbol, tick, onClose, onGo }: { symbol: string; tick: number; onClose: () => void; onGo: (screen: string, symbol: string) => void }) {
  const [s, setS] = useState<Stock | null>(null);
  useEffect(() => { setS(null); getJSON<Stock>(`/api/stock/${encodeURIComponent(symbol)}`).then(setS); }, [symbol, tick]);
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`About ${symbol}`}>
        <div className="drawer-head">
          <div><div className="drawer-symbol">{symbol}</div><div className="muted">{s?.status === "OK" ? s.name : ""}</div></div>
          <button onClick={onClose} aria-label="Close">Close</button>
        </div>
        {!s ? <p className="muted">Loading</p> : s.status !== "OK" ? <p className="na">NOT AVAILABLE. {s.reason}</p> : (
          <>
            <div className="price-line">
              <span className="big">{s.price.last?.toFixed(2) ?? "NOT AVAILABLE"}</span>
              <span className="muted small">USD, close {s.price.date}, {s.price.source}</span>
            </div>
            <div className="changes">
              {Object.entries(s.price.change).map(([k, v]) => { const c = signed(v, (x) => pct(x, 1)); return <div key={k}><div className="muted small">{k} (%)</div><div className={c.cls}>{c.text}</div></div>; })}
            </div>
            <Chart points={s.history} />
            <section className="block"><h3>What the company is</h3>
              <p>{s.name}. Industry: {s.industry.plain}.</p>
              <p className="muted small">{s.tag_note}.{s.type_inferred ? " Security type inferred from its name." : ""}</p>
            </section>
            <section className="block"><h3>What the system thinks</h3>
              <p>{s.system_view}</p>
              {s.proposal && <p>Planned for {s.proposal.session_date}: {sideLabel(s.proposal.side).replace(/^[▲▼] /, "").toLowerCase()} {s.proposal.quantity} shares, status {s.proposal.status}.</p>}
              <p className="muted small">How much it swings: {s.price.volatility_annual === null ? "NOT AVAILABLE" : `${pct(s.price.volatility_annual, 0)}% a year`}. Composite score: {s.composite_score === null ? "NOT AVAILABLE" : s.composite_score.toFixed(2)}.</p>
              <button className="link" onClick={() => onGo("reasoning", s.symbol)}>Full reasoning</button>
            </section>
            <section className="block"><h3>News that names it</h3>
              {(s.news ?? []).length === 0 ? <p className="muted">No stories in the last 90 days</p> : (
                <ul className="plain">{s.news!.map((n) => <li key={n.cluster_id}><span className="muted small">{timeET(n.first_usable_at)}{n.category ? `, ${n.category.label}` : ""}</span><br /><span data-source-text>{n.headline}</span></li>)}</ul>)}
            </section>
          </>)}
      </aside>
    </>
  );
}
