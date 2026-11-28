import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { licenseName, modelName, plainReason, signalName, vendorName } from "../labels";
import { Tech } from "../stock";
import { timeET, sideLabel } from "../format";

type R = {
  symbol: string; status: string; reason?: string;
  proposal: { side: string; quantity: number; status: string; reason: string; session_date: string } | null;
  forecast: { model_id: string; model_version: string; signal_strength: number; as_of: string; calibration_status: string; data_snapshot_id: string; record_type: string; data_licenses: string[] } | null;
  risk: { verdict: string; reasons: string[]; checks_run: string[]; decided_at: string } | null;
  composite: { run_id: string | null; record_type: string | null; agreeing: [string, number][]; opposing: [string, number][]; exclusions: { signal_id: string; reasons: string[] }[]; uncertainty: { signal_id: string; mu_hat: number; prob_positive: number }[] };
  freshness: { last_close_date?: string; usable_from?: string; vendor?: string; status?: string };
  news: { title: string; feed: string; usable_from: string; link: string }[];
  why_not: string | null;
};

export function ReasoningScreen({ tick, initial }: { tick: number; initial?: string }) {
  const [symbol, setSymbol] = useState(initial ?? "UPCO");
  const [query, setQuery] = useState(initial ?? "UPCO");
  useEffect(() => { if (initial) { setSymbol(initial); setQuery(initial); } }, [initial]);
  const [data, setData] = useState<R | null>(null);
  useEffect(() => { getJSON<R>(`/api/reasoning?symbol=${encodeURIComponent(query)}`).then(setData); }, [tick, query]);
  return (
    <>
      <section className="panel"><h2>Reasoning for one ticker</h2>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(symbol.toUpperCase()); }} style={{ display: "flex", gap: 8 }}>
          <input aria-label="Ticker" value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ font: "inherit", background: "transparent", color: "var(--text)", border: "var(--panel-border)", borderRadius: "var(--radius)", padding: "4px 8px" }} />
          <button type="submit">Explain</button>
        </form>
      </section>
      {!data ? <div className="panel muted">Loading</div> : data.status !== "OK" ? <div className="panel na">NOT AVAILABLE. {data.reason}</div> : (
        <>
          {data.why_not && <section className="panel"><h2>Why not?</h2><p>{plainReason(data.why_not)}</p></section>}
          <div className="grid2">
            <section className="panel"><h2>Evidence</h2>
              {data.forecast ? (<table><tbody>
                <tr><td>Model</td><td>{modelName(data.forecast.model_id)}</td></tr>
                <tr><td>Signal strength</td><td className="num">{data.forecast.signal_strength.toFixed(2)}</td></tr>
                <tr><td>Calibrated</td><td>{data.forecast.calibration_status === "calibrated" ? "Yes" : "No. The strength ranks names but is not a forecast"}</td></tr>
                <tr><td>Decided at</td><td>{timeET(data.forecast.as_of)}</td></tr>
                <tr><td>Data used</td><td>{(data.forecast.data_licenses ?? []).map(licenseName).join(", ")}</td></tr>
              </tbody></table>) : <p className="na">Not available. No forecast recorded for this ticker</p>}
              {data.forecast && <Tech><p>Model {data.forecast.model_id} version {data.forecast.model_version}. Data snapshot {data.forecast.data_snapshot_id}. Calibration status {data.forecast.calibration_status}.</p></Tech>}
            </section>
            <section className="panel"><h2>Data freshness</h2>
              {data.freshness.last_close_date ? <p>Last close {data.freshness.last_close_date}, known from {timeET(data.freshness.usable_from)}. Source: {vendorName(data.freshness.vendor)}.</p> : <p className="na">Not available</p>}
              <h2>Order and risk check</h2>
              {data.proposal ? <p>{sideLabel(data.proposal.side)} {data.proposal.quantity} for {data.proposal.session_date}, status {data.proposal.status.toUpperCase()}</p> : <p className="muted">No proposal</p>}
              {data.risk ? (<><p>Risk check {data.risk.verdict === "approved" ? "passed" : "blocked the order"} at {timeET(data.risk.decided_at)}, {data.risk.checks_run.length} checks.</p>
                {data.risk.reasons.length > 0 && <ul>{data.risk.reasons.map((r, i) => <li key={i}>{plainReason(r)}</li>)}</ul>}</>) : <p className="muted">No risk check recorded</p>}
            </section>
          </div>
          <div className="grid2">
            <section className="panel"><h2>Agreeing and opposing signals</h2>
              {data.composite.agreeing.length + data.composite.opposing.length === 0 && <p className="muted">None. No signal holds weight in the Composite, so none contributes to this ticker's score.</p>}
              <table><thead><tr><th>Signal</th><th>Direction</th><th className="num">Share of score</th></tr></thead><tbody>
                {data.composite.agreeing.map(([s, v]) => <tr key={s}><td>{signalName(s)}</td><td className="gain">▲ agrees</td><td className="num">{v.toFixed(2)}</td></tr>)}
                {data.composite.opposing.map(([s, v]) => <tr key={s}><td>{signalName(s)}</td><td className="loss">▼ opposes</td><td className="num">{v.toFixed(2)}</td></tr>)}
              </tbody></table>
              <h2 style={{ marginTop: 12 }}>How sure the system is</h2>
              <table><thead><tr><th>Signal</th><th className="num">Expected edge (% a year)</th><th className="num">Chance the edge is real (%)</th></tr></thead><tbody>
                {data.composite.uncertainty.map((u) => <tr key={u.signal_id}><td>{signalName(u.signal_id)}</td><td className="num">{(u.mu_hat * 100).toFixed(1)}</td><td className="num">{(u.prob_positive * 100).toFixed(0)}</td></tr>)}
              </tbody></table>
            </section>
            <section className="panel"><h2>Signals left out, and why</h2>
              {data.composite.exclusions.map((x) => <div key={x.signal_id}><p><strong>{signalName(x.signal_id)}</strong></p><ul>{x.reasons.map((r, i) => <li key={i} className="muted">{plainReason(r)}</li>)}</ul></div>)}
              <h2>News for this ticker</h2>
              {data.news.length === 0 ? <p className="muted">No linked stories</p> : <ul>{data.news.map((n, i) => <li key={i}>{timeET(n.usable_from)} {n.title}</li>)}</ul>}
            </section>
          </div>
        </>)}
    </>
  );
}
