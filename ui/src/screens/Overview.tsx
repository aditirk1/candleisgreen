import { useEffect, useRef, useState } from "react";
import { createChart, LineSeries, UTCTimestamp } from "lightweight-charts";
import { getJSON, Overview } from "../api";
import { pct, signed, timeET, usd } from "../format";
import { Term } from "../guide";
import { Ticker } from "../stock";

const MIN_POINTS = 5;
type Opp = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; status: string };
type Story = { cluster_id: string; headline: string; first_usable_at: string; tickers: string[]; category: { label: string } | null };

function EquityCurve({ points }: { points: Overview["equity_curve"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || points.length < MIN_POINTS) return;
    const css = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, {
      height: 200, layout: { background: { color: "transparent" }, textColor: css.getPropertyValue("--muted").trim() },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } }, timeScale: { borderVisible: false }, rightPriceScale: { borderVisible: false },
    });
    chart.addSeries(LineSeries, { color: css.getPropertyValue("--accent").trim(), lineWidth: 2 })
      .setData(points.map((p) => ({ time: Math.floor(new Date(p.time).getTime() / 1000) as UTCTimestamp, value: p.value })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  if (points.length < MIN_POINTS) return <p className="muted">The chart appears after {MIN_POINTS} decision runs. {points.length} so far.</p>;
  return <div ref={ref} aria-label="Equity curve" />;
}

export function OverviewScreen({ tick, onGo }: { tick: number; onGo: (screen: string) => void }) {
  const [data, setData] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<{ session_date: string | null; rows: Opp[] } | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getJSON<Overview>("/api/overview").then(setData).catch((e) => setErr(String(e)));
    getJSON<{ session_date: string | null; rows: Opp[] }>("/api/opportunities").then(setPlan).catch(() => setPlan(null));
    getJSON<{ clusters: Story[] }>("/api/news?view=recent").then((d) => setStories(d.clusters.slice(0, 4))).catch(() => setStories([]));
  }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  const change = signed(data.todays_change, usd);
  const pending = (plan?.rows ?? []).filter((r) => r.status === "proposed");
  return (
    <div className="page">
      {data.alerts.length > 0 && (
        <div className="alerts" role="status">{data.alerts.slice(0, 3).map((a, i) => <div key={i} title={a.detail}>▲ {a.symbol ? `${a.symbol} ` : ""}{a.event}, {timeET(a.time)}</div>)}</div>)}
      <section className="kpis">
        <div className="panel kpi"><div className="label">Account value (USD)</div><div className="value">{usd(data.account_value)}</div></div>
        <div className="panel kpi"><div className="label">Change since last decision (USD)</div><div className={`value ${change.cls}`}>{change.text}</div></div>
        <div className="panel kpi"><div className="label">Invested (% of account)</div><div className="value">{pct(data.risk_in_use.invested_pct, 1)}</div>
          <div className="label">Largest position {pct(data.risk_in_use.largest_position_pct, 1)}% of a {pct(data.risk_in_use.position_limit_pct, 0)}% limit</div></div>
      </section>
      <div className="grid2 even">
        <section className="panel"><h2>Next session plan{plan?.session_date ? `, ${plan.session_date}` : ""}</h2>
          {!plan || plan.rows.length === 0 ? <p className="muted">Nothing planned. The next decision runs after the close.</p> : (
            <>
              <ul className="plain list">{plan.rows.slice(0, 6).map((r) => (
                <li key={r.proposal_id}><Ticker symbol={r.symbol} /> <span>{r.side === "buy" ? "▲ Buy" : "▼ Sell"} {r.quantity} {r.quantity === 1 ? "share" : "shares"}</span>
                  <span className="muted small"> <Term k="signal_strength">trend strength</Term> {r.signal_strength?.toFixed(2) ?? "NOT AVAILABLE"}</span>
                  <span className="status">{r.status}</span></li>))}
              </ul>
              {pending.length > 0 && <button className="primary" onClick={() => onGo("execution")}>Review {pending.length} waiting for approval</button>}
            </>)}
        </section>
        <section className="panel"><h2>Top stories</h2>
          {stories.length === 0 ? <p className="muted">No recent stories</p> : (
            <ul className="plain list">{stories.map((s) => (
              <li key={s.cluster_id}><span className="muted small">{s.category?.label ?? "News"}{s.tickers.length ? `, ${s.tickers.join(", ")}` : ""}</span><br /><button className="link left" onClick={() => onGo("news")} data-source-text>{s.headline}</button></li>))}
            </ul>)}
        </section>
      </div>
      <section className="panel"><h2>Holdings</h2>
        {data.positions.length === 0 ? <p className="muted">No positions</p> : (
          <table><thead><tr><th>Ticker</th><th className="num">Shares</th><th className="num">Price (USD)</th><th className="num">Value (USD)</th><th className="num">Weight (%)</th></tr></thead>
            <tbody>{data.positions.map((p) => (
              <tr key={p.instrument_id} title={p.price_source}><td><Ticker symbol={p.symbol} /></td><td className="num">{p.quantity}</td><td className="num">{usd(p.price)}</td>
                <td className="num">{usd(p.market_value)}</td><td className="num">{pct(p.weight)}</td></tr>))}
            </tbody></table>)}
      </section>
      <details className="panel"><summary>Account value over time</summary><EquityCurve points={data.equity_curve} /></details>
    </div>
  );
}
