import { useEffect, useRef, useState } from "react";
import { createChart, LineSeries, UTCTimestamp } from "lightweight-charts";
import { getJSON, Overview } from "../api";
import { pct, signed, timeET, usd } from "../format";

function EquityCurve({ points }: { points: Overview["equity_curve"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    const css = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, {
      height: 220, layout: { background: { color: "transparent" }, textColor: css.getPropertyValue("--muted").trim() },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } }, timeScale: { borderVisible: false },
    });
    const series = chart.addSeries(LineSeries, { color: css.getPropertyValue("--accent").trim(), lineWidth: 2 });
    series.setData(points.map((p) => ({ time: Math.floor(new Date(p.time).getTime() / 1000) as UTCTimestamp, value: p.value })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  if (points.length === 0) return <p className="na">NOT AVAILABLE. No decision run has recorded equity yet.</p>;
  return <div ref={ref} aria-label="Equity curve" />;
}

export function OverviewScreen({ tick }: { tick: number }) {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getJSON<Overview>("/api/overview").then(setData).catch((e) => setErr(String(e))); }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  const change = signed(data.todays_change, usd);
  return (
    <>
      <section className="kpis">
        <div className="panel kpi"><div className="label">Account value (USD)</div><div className="value">{usd(data.account_value)}</div></div>
        <div className="panel kpi"><div className="label">Change since last decision (USD)</div><div className={`value ${change.cls}`}>{change.text}</div></div>
        <div className="panel kpi"><div className="label">Risk in use, invested (% of equity)</div><div className="value">{pct(data.risk_in_use.invested_pct)}</div>
          <div className="label">Largest position {pct(data.risk_in_use.largest_position_pct)} of {pct(data.risk_in_use.position_limit_pct, 0)} limit</div></div>
      </section>
      <div className="grid2">
        <section className="panel"><h2>Equity curve</h2><EquityCurve points={data.equity_curve} /></section>
        <section className="panel"><h2>Alerts</h2>
          {data.alerts.length === 0 ? <p className="muted">No alerts</p> : (
            <table><thead><tr><th>Ticker</th><th>Event</th><th>Time</th></tr></thead><tbody>
              {data.alerts.map((a, i) => <tr key={i} title={a.detail}><td>{a.symbol}</td><td>{a.event}</td><td>{timeET(a.time)}</td></tr>)}
            </tbody></table>)}
        </section>
      </div>
      <section className="panel"><h2>Positions</h2>
        {data.positions.length === 0 ? <p className="muted">No positions</p> : (
          <table><thead><tr><th>Ticker</th><th className="num">Shares</th><th className="num">Price (USD)</th><th className="num">Value (USD)</th><th className="num">Weight (%)</th><th>Price source</th></tr></thead>
            <tbody>{data.positions.map((p) => (
              <tr key={p.instrument_id}><td>{p.symbol}</td><td className="num">{p.quantity}</td><td className="num">{usd(p.price)}</td>
                <td className="num">{usd(p.market_value)}</td><td className="num">{pct(p.weight)}</td><td className="muted">{p.price_source}</td></tr>))}
            </tbody></table>)}
      </section>
    </>
  );
}
