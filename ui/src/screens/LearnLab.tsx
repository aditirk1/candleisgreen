import { Fragment, useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { timeET, usd } from "../format";

type Autopsy = { fill_id: string; symbol: string; side: string; quantity: number; fill_price: number; filled_at: string; expected_catalyst: string; window: { end: string; status: string }; spread_paid_bps: number | null; what_happened: string; pnl: { total_usd: number; price_move_usd: number; spread_cost_usd: number; market_usd: number | null; specific_usd: number | null; market_method: string } | null; assumptions: { assumption: string; result: string }[] };
type CF = { label: string; status: string; reason?: string; baseline?: { signal: number; decision: string }; hypothetical?: { signal: number | null; decision: string }; changed?: boolean; note?: string };
type Card = { card_id: string; kind: string; prompt: string; answer: string; box: number };
type Crisis = { name: string; start: string; end: string; status: string; reason: string | null; what_current_rules_would_do: string };

const CHANGES: [string, string, number][] = [["vol_multiplier", "Multiply volatility by", 2], ["last_price_pct", "Move the latest close by (%)", -10], ["spread_bps", "Set the spread to (bps)", 50], ["remove_news", "Remove a news story", 0]];

export function LearnLab({ tick, cursor }: { tick: number; cursor: string }) {
  const [autopsy, setAutopsy] = useState<Autopsy[]>([]);
  const [cf, setCf] = useState<CF | null>(null);
  const [cfForm, setCfForm] = useState({ symbol: "UPCO", change: "vol_multiplier", amount: 2 });
  const [cards, setCards] = useState<Card[]>([]);
  const [shown, setShown] = useState(false);
  const [crises, setCrises] = useState<Crisis[]>([]);
  const [n, setN] = useState(0);
  useEffect(() => { getJSON<{ rows: Autopsy[] }>("/api/autopsy").then((d) => setAutopsy(d.rows)); }, [tick]);
  useEffect(() => { getJSON<{ cards: Card[] }>(`/api/review?cursor=${encodeURIComponent(cursor)}`).then((d) => { setCards(d.cards); setShown(false); }); }, [tick, cursor, n]);
  useEffect(() => { getJSON<{ episodes: Crisis[] }>("/api/crises").then((d) => setCrises(d.episodes)); }, [tick]);

  async function runCf() {
    const q = new URLSearchParams({ symbol: cfForm.symbol, change: cfForm.change, amount: String(cfForm.amount) });
    setCf(await getJSON<CF>(`/api/counterfactual?${q}`).catch((e) => ({ label: "HYPOTHETICAL", status: "NOT AVAILABLE", reason: String(e) })));
  }
  async function grade(correct: boolean) { await post(`/api/review/${cards[0].card_id}`, { correct }); setN((x) => x + 1); }
  const card = cards[0];
  return (
    <>
      <section className="panel"><h2>Market autopsy, simulated trades</h2>
        {autopsy.length === 0 ? <p className="muted">No simulated fills yet</p> : autopsy.map((a) => (
          <div key={a.fill_id} style={{ marginBottom: 12 }}>
            <p><strong>{a.side === "buy" ? "▲ BUY" : "▼ SELL"} {a.quantity} {a.symbol} at {a.fill_price.toFixed(2)}</strong>, {timeET(a.filled_at)}. Window {a.window.status}, ends {a.window.end.slice(0, 10)}.</p>
            <dl className="facts">
              <dt>Expected catalyst</dt><dd>{a.expected_catalyst}</dd>
              <dt>What happened</dt><dd>{a.what_happened}</dd>
              <dt>Spread paid (bps)</dt><dd>{a.spread_paid_bps === null ? "NOT AVAILABLE" : a.spread_paid_bps.toFixed(2)}</dd>
              {a.pnl && <><dt>Profit and loss (USD)</dt><dd>Total {usd(a.pnl.total_usd)}. Price move {usd(a.pnl.price_move_usd)}, spread {usd(a.pnl.spread_cost_usd)}. Market {usd(a.pnl.market_usd)}, specific {usd(a.pnl.specific_usd)}</dd></>}
              {a.assumptions.map((x) => <Fragment key={x.assumption}><dt>{x.assumption}</dt><dd>{x.result}</dd></Fragment>)}
            </dl>
          </div>))}
      </section>
      <div className="grid2">
        <section className="panel"><h2>Counterfactual, hypothetical only</h2>
          <form onSubmit={(e) => { e.preventDefault(); runCf(); }} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input aria-label="Counterfactual ticker" className="field" value={cfForm.symbol} onChange={(e) => setCfForm({ ...cfForm, symbol: e.target.value.toUpperCase() })} />
            <select aria-label="Change" className="field" value={cfForm.change} onChange={(e) => { const c = CHANGES.find((x) => x[0] === e.target.value)!; setCfForm({ ...cfForm, change: c[0], amount: c[2] }); }}>
              {CHANGES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            {cfForm.change !== "remove_news" && <input aria-label="Amount" className="field" type="number" value={cfForm.amount} onChange={(e) => setCfForm({ ...cfForm, amount: Number(e.target.value) })} />}
            <button type="submit">Test the change</button>
          </form>
          {cf && (cf.status !== "OK" ? <p className="na">NOT AVAILABLE. {cf.reason}</p> : (
            <dl className="facts">
              <dt>Label</dt><dd>{cf.label}</dd>
              <dt>Recorded decision</dt><dd>{cf.baseline!.decision}, signal {cf.baseline!.signal.toFixed(3)}</dd>
              <dt>After the change</dt><dd>{cf.hypothetical!.decision}{cf.hypothetical!.signal === null ? "" : `, signal ${cf.hypothetical!.signal.toFixed(3)}`}</dd>
              <dt>Decision changes</dt><dd>{cf.changed ? "Yes" : "No"}</dd>
              <dt>Why</dt><dd>{cf.note}</dd>
            </dl>))}
        </section>
        <section className="panel"><h2>Spaced review</h2>
          {!card ? <p className="muted">No cards due</p> : (<>
            <p className="muted">{card.kind === "wrong_prediction" ? "From your own wrong prediction" : "Glossary"}. Box {card.box}. {cards.length} due.</p>
            <p>{card.prompt}</p>
            {shown ? (<><p>{card.answer}</p><div style={{ display: "flex", gap: 8 }}><button onClick={() => grade(true)}>I knew it</button><button onClick={() => grade(false)}>I did not</button></div></>)
              : <button onClick={() => setShown(true)}>Show answer</button>}
          </>)}
        </section>
      </div>
      <section className="panel"><h2>Crisis library</h2>
        <table><thead><tr><th>Episode</th><th>Start</th><th>End</th><th>Status</th><th>What current rules would have done</th></tr></thead>
          <tbody>{crises.map((c) => <tr key={c.name}><td>{c.name}</td><td>{c.start}</td><td>{c.end}</td><td className={c.status === "AVAILABLE" ? "" : "na"}>{c.status}{c.reason ? `. ${c.reason}` : ""}</td><td className="muted">{c.what_current_rules_would_do}</td></tr>)}</tbody></table>
      </section>
    </>
  );
}
