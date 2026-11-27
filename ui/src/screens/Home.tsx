import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { PriceChart } from "../chart";
import { MODE_LABELS, pct, sideLabel, signed, timeET, usd } from "../format";
import { Ticker } from "../stock";
import { load, useMode } from "../theme";

type Position = { instrument_id: string; symbol: string; quantity: number; price: number | null; market_value: number | null; weight: number | null; price_source: string };
type Home = {
  venue: string; mode: string; now: string;
  data: { kind: string; note: string };
  market: { status: string; trading_day: boolean; local_time: string };
  account: { value: number; cash: number; starting_value: number; change_since_last_decision: number; change_since_start: number; change_since_start_pct: number; invested_pct: number; short_pct: number };
  performance: { time: string; value: number }[];
  needs_attention: { severity: string; text: string; screen: string }[];
  system_health: { part: string; status: string; detail: string }[];
  positions: Position[];
};
type Story = { cluster_id: string; headline: string; first_usable_at: string; tickers: string[]; category: { label: string } | null; rank: { materiality: string; score: number } };
type Opp = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; status: string; direction?: string };
type Watch = { symbol: string; price: number | null; change: number | null; status: string };
const MIN_POINTS = 5;
const ICON: Record<string, string> = { critical: "▲", action: "●", info: "○" };

export function HomeScreen({ tick, onGo }: { tick: number; onGo: (screen: string) => void; onKill: () => void }) {
  const mode = useMode();
  const [h, setH] = useState<Home | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [stories, setStories] = useState<Story[] | null>(null);
  const [opps, setOpps] = useState<{ session_date: string | null; rows: Opp[] } | null>(null);
  const [watch, setWatch] = useState<Watch[]>([]);
  useEffect(() => {
    getJSON<Home>("/api/home").then(setH).catch((e) => setErr(String(e)));
    getJSON<{ clusters: Story[] }>("/api/news?view=recent").then((d) => setStories(d.clusters.filter((c) => c.rank?.materiality === "MATERIAL").slice(0, 3))).catch(() => setStories([]));
    getJSON<{ session_date: string | null; rows: Opp[] }>("/api/opportunities").then(setOpps).catch(() => setOpps(null));
    let list: string[] = [];
    try { list = JSON.parse(load("watchlist") ?? "[]"); } catch { list = []; }
    Promise.all(list.slice(0, 8).map((s) => getJSON<{ status: string; price?: { last: number | null; change: Record<string, number | null> } }>(`/api/stock/${encodeURIComponent(s)}`)
      .then((d) => ({ symbol: s, status: d.status, price: d.price?.last ?? null, change: d.price?.change["1 day"] ?? null }))
      .catch(() => ({ symbol: s, status: "NOT AVAILABLE", price: null, change: null })))).then(setWatch);
  }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!h) return <div className="panel muted">Loading</div>;
  const a = h.account;
  const total = signed(a.change_since_start, usd);
  const last = signed(a.change_since_last_decision, usd);
  const top = [...(opps?.rows ?? [])].filter((r) => r.status !== "rejected").sort((x, y) => Math.abs(y.signal_strength ?? 0) - Math.abs(x.signal_strength ?? 0)).slice(0, 5);
  const critical = h.system_health.some((x) => x.status !== "OK" && x.status !== "NOT RUN");
  return (
    <div className="page home">
      {h.data.kind !== "LIVE" && <div className={h.data.kind === "SYNTHETIC" ? "data-banner" : "data-banner none"} role="note"><strong>{h.data.kind === "SYNTHETIC" ? "DEMO DATA." : "NO DATA."}</strong> {h.data.note}.</div>}

      <section className="summary" aria-label="Account summary">
        <div className="metric main"><div className="label">Account value (USD)</div><div className="value">{usd(a.value)}</div></div>
        <div className="metric"><div className="label">Profit and loss since start (USD)</div><div className={`value ${total.cls}`}>{total.text}</div>
          <div className="label">{pct(a.change_since_start_pct, 2)}% of {usd(a.starting_value)}</div></div>
        <div className="metric"><div className="label">Since last decision (USD)</div><div className={`value ${last.cls}`}>{last.text}</div></div>
        <div className="metric"><div className="label">Invested, long plus short (%)</div><div className="value">{pct(a.invested_pct, 1)}</div>
          {a.short_pct > 0 && <div className="label">Short {pct(a.short_pct, 1)}%</div>}</div>
        <div className="metric"><div className="label">Account</div><div className="value small-value">{h.venue}</div><div className="label">{MODE_LABELS[h.mode] ?? h.mode}</div></div>
        <div className="metric"><div className="label">US market</div><div className="value small-value">{h.market.status}</div><div className="label">{h.market.trading_day ? `${h.market.local_time} ET` : "Not a trading day"}</div></div>
      </section>

      <section className="panel"><h2>Performance</h2>
        {h.performance.length < MIN_POINTS
          ? <p className="muted">Not enough history yet. {h.performance.length} decision runs recorded. The chart starts at {MIN_POINTS}.</p>
          : <PriceChart label="Account value" candles={false} height={240} bars={h.performance.map((p) => ({ date: p.time, close: p.value }))} defaultRange="All" />}
      </section>

      <div className="grid2 even">
        <section className="panel attention"><h2>Needs attention</h2>
          {h.needs_attention.length === 0 ? <p className="muted">Nothing needs your attention.</p> : (
            <ul className="plain list">{h.needs_attention.map((n, i) => (
              <li key={i} className={`sev-${n.severity}`}><span aria-hidden>{ICON[n.severity] ?? "●"}</span> <span>{n.text}</span>
                <button className="link right" onClick={() => onGo(n.screen)}>Open</button></li>))}
            </ul>)}
        </section>
        <section className="panel"><h2>Market developments</h2>
          {stories === null ? <p className="muted">Loading</p> : stories.length === 0 ? <p className="muted">No material stories in the last 90 days.</p> : (
            <ul className="plain list">{stories.map((s) => (
              <li key={s.cluster_id}><span className="muted small">{s.category?.label ?? "News"}{s.tickers.length ? `, ${s.tickers.join(", ")}` : ""}, {timeET(s.first_usable_at)}</span><br />
                <button className="link left" onClick={() => onGo("news")} data-source-text>{s.headline}</button></li>))}
            </ul>)}
        </section>
      </div>

      <section className="panel"><h2>Top research opportunities{opps?.session_date ? `, ${opps.session_date}` : ""}</h2>
        {top.length === 0 ? <p className="muted">No proposals yet. The next decision runs after the close.</p> : (
          <table><thead><tr><th>Ticker</th><th>Proposal</th><th className="num">Signal strength</th><th>Status</th></tr></thead>
            <tbody>{top.map((r) => (
              <tr key={r.proposal_id}><td><Ticker symbol={r.symbol} /></td><td>{sideLabel(r.side)} {r.quantity}</td>
                <td className="num">{r.signal_strength?.toFixed(2) ?? "NOT AVAILABLE"}</td><td>{r.status}</td></tr>))}
            </tbody></table>)}
        <button className="link" onClick={() => onGo("opportunities")}>All opportunities</button>
      </section>

      <div className="grid2 even">
        <section className="panel"><h2>Watchlist</h2>
          {watch.length === 0 ? <p className="muted">Empty. Add tickers from Markets.</p> : (
            <table><thead><tr><th>Ticker</th><th className="num">Price (USD)</th><th className="num">1 day (%)</th></tr></thead>
              <tbody>{watch.map((w) => { const c = signed(w.change, (x) => pct(x, 2)); return (
                <tr key={w.symbol}><td><Ticker symbol={w.symbol} /></td><td className="num">{w.status === "OK" ? usd(w.price) : "NOT AVAILABLE"}</td><td className={`num ${c.cls}`}>{c.text}</td></tr>); })}
              </tbody></table>)}
        </section>
        <section className="panel"><h2>Positions</h2>
          {h.positions.length === 0 ? <p className="muted">No positions.</p> : (
            <table><thead><tr><th>Ticker</th><th className="num">Shares</th><th className="num">Value (USD)</th><th className="num">Weight (%)</th></tr></thead>
              <tbody>{h.positions.map((p) => (
                <tr key={p.instrument_id} title={p.price_source}><td><Ticker symbol={p.symbol} /></td><td className="num">{p.quantity}</td>
                  <td className="num">{usd(p.market_value)}</td><td className="num">{pct(p.weight)}</td></tr>))}
              </tbody></table>)}
        </section>
      </div>

      <details className="panel" open={mode === "advanced" || critical}>
        <summary>System health{critical ? ", needs attention" : ""}</summary>
        <table><thead><tr><th>Part</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>{h.system_health.map((x) => <tr key={x.part}><td>{x.part}</td><td className={x.status === "OK" ? "gain" : x.status === "NOT RUN" ? "muted" : "loss"}>{x.status === "OK" ? "✓ OK" : x.status}</td><td className="muted">{x.detail}</td></tr>)}</tbody></table>
      </details>
    </div>
  );
}
