import { useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { timeET } from "../format";
import { LearnLab } from "./LearnLab";

type Pred = { prediction_id: string; symbol: string; direction: string; horizon_days: number; probability: number; made_at: string; context: string; outcome: number | null; status: string };
type Cal = { bins: { range: string; count: number; mean_stated: number | null; hit_rate: number | null }[]; brier: number | null; baseline_brier: number; resolved: number };
type View = { cursor: string; symbol: string; prices: { date: string; value: number; vintage: number }[]; news: { title: string; usable_from: string }[]; intraday: string };

const input = { font: "inherit", background: "transparent", color: "var(--text)", border: "var(--panel-border)", borderRadius: "var(--radius)", padding: "4px 8px" } as const;

const LEARN_TABS: [string, string][] = [["practice", "Practice"], ["lessons", "Lessons"], ["trades", "Your trades"], ["experiments", "Experiments"]];

export function LearnScreen({ tick }: { tick: number }) {
  const [tab, setTab] = useState("practice");
  const [cursor, setCursor] = useState("2026-10-01T21:30:00+00:00");
  const [symbol, setSymbol] = useState("UPCO");
  const [view, setView] = useState<View | null>(null);
  const [preds, setPreds] = useState<{ predictions: Pred[]; calibration: Cal } | null>(null);
  const [form, setForm] = useState({ direction: "up", horizon_days: 5, probability: 0.6 });
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { getJSON<View>(`/api/replay?symbol=${symbol}&cursor=${encodeURIComponent(cursor)}`).then(setView); }, [cursor, symbol, tick]);
  useEffect(() => { getJSON<{ predictions: Pred[]; calibration: Cal }>(`/api/predictions?cursor=${encodeURIComponent(cursor)}`).then(setPreds); }, [cursor, tick, pending]);

  async function predict() {
    const r = await post("/api/predictions", { symbol, ...form, replay_cursor: cursor });
    setMsg(r.ok ? "Prediction recorded. Advance the replay to reveal the outcome." : `Prediction refused (${r.status})`);
    setPending(!pending);
  }
  function advance(days: number) {
    const d = new Date(cursor); d.setUTCDate(d.getUTCDate() + days); setCursor(d.toISOString().replace(".000Z", "+00:00"));
  }
  return (
    <div className="page">
      <div className="page-head"><h1>Learn</h1>
        <div className="segmented" role="group" aria-label="Learn sections">
          {LEARN_TABS.map(([k, label]) => <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>)}
        </div>
      </div>
      {tab === "practice" && (<>
      <section className="panel"><h2>Replay, as known then</h2>
        <p>Replay clock {timeET(cursor)}. Prices, news and corrections appear only after the time they were first usable. {view?.intraday}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="Replay ticker" style={input} value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          <button onClick={() => advance(1)}>Advance 1 day</button><button onClick={() => advance(5)}>Advance 5 days</button>
        </div>
        <div className="grid2" style={{ marginTop: 8 }}>
          <table><thead><tr><th>Date</th><th className="num">Close (USD)</th><th className="num">Vintage</th></tr></thead>
            <tbody>{(view?.prices ?? []).slice(-8).map((p) => <tr key={p.date}><td>{p.date}</td><td className="num">{p.value.toFixed(2)}</td><td className="num">{p.vintage}</td></tr>)}</tbody></table>
          <div><h2>Headlines known then</h2>{(view?.news ?? []).length === 0 ? <p className="muted">None yet</p> : <ul>{view!.news.slice(0, 6).map((n, i) => <li key={i}>{n.title}</li>)}</ul>}</div>
        </div>
      </section>
      <section className="panel"><h2>Predict first</h2>
        <p className="muted">State direction, horizon and probability before the reveal. Scored with the Brier score against a 50% baseline.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select aria-label="Direction" style={input} value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}><option value="up">Up</option><option value="down">Down</option></select>
          <label>Horizon (days) <input aria-label="Horizon" type="number" min={1} max={60} style={{ ...input, width: 70 }} value={form.horizon_days} onChange={(e) => setForm({ ...form, horizon_days: Number(e.target.value) })} /></label>
          <label>Probability (%) <input aria-label="Probability" type="number" min={0} max={100} style={{ ...input, width: 70 }} value={Math.round(form.probability * 100)} onChange={(e) => setForm({ ...form, probability: Number(e.target.value) / 100 })} /></label>
          <button onClick={predict}>Record prediction for {symbol}</button>
        </div>
        {msg && <p>{msg}</p>}
      </section>
      <div className="grid2">
        <section className="panel"><h2>My predictions</h2>
          <table><thead><tr><th>Ticker</th><th>Call</th><th className="num">Days</th><th className="num">Probability (%)</th><th>Made (replay clock)</th><th>Result</th></tr></thead>
            <tbody>{(preds?.predictions ?? []).map((p) => (
              <tr key={p.prediction_id}><td>{p.symbol}</td><td>{p.direction.toUpperCase()}</td><td className="num">{p.horizon_days}</td><td className="num">{Math.round(p.probability * 100)}</td>
                <td>{timeET(p.made_at)}</td><td className={p.outcome === 1 ? "gain" : p.outcome === 0 ? "loss" : "muted"}>{p.outcome === 1 ? "▲ RIGHT" : p.outcome === 0 ? "▼ WRONG" : p.status}</td></tr>))}
            </tbody></table>
        </section>
        <section className="panel"><h2>Calibration</h2>
          <p>Brier score {preds?.calibration.brier === null || preds === null ? "NOT AVAILABLE" : preds.calibration.brier.toFixed(3)} against a baseline of {preds?.calibration.baseline_brier.toFixed(2)}, from {preds?.calibration.resolved ?? 0} resolved predictions. Lower is better.</p>
          <table><thead><tr><th>Stated probability</th><th className="num">Count</th><th className="num">Hit rate (%)</th></tr></thead>
            <tbody>{(preds?.calibration.bins ?? []).map((b) => <tr key={b.range}><td>{b.range}</td><td className="num">{b.count}</td><td className="num">{b.hit_rate === null ? "NOT AVAILABLE" : Math.round(b.hit_rate * 100)}</td></tr>)}</tbody></table>
        </section>
      </div>
      </>)}
      {tab !== "practice" && <LearnLab tick={tick} cursor={cursor} part={tab} />}
    </div>
  );
}
