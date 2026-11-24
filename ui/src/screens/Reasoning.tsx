import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { timeET } from "../format";

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
          {data.why_not && <section className="panel"><h2>Why not?</h2><p>{data.why_not}</p></section>}
          <div className="grid2">
            <section className="panel"><h2>Evidence</h2>
              {data.forecast ? (<table><tbody>
                <tr><td>Model</td><td>{data.forecast.model_id} {data.forecast.model_version}</td></tr>
                <tr><td>Signal strength</td><td className="num">{data.forecast.signal_strength.toFixed(2)}</td></tr>
                <tr><td>Calibration</td><td>{data.forecast.calibration_status.toUpperCase()}</td></tr>
                <tr><td>Decision time</td><td>{timeET(data.forecast.as_of)}</td></tr>
                <tr><td>Data snapshot</td><td className="muted">{data.forecast.data_snapshot_id}</td></tr>
                <tr><td>Data licenses</td><td>{(data.forecast.data_licenses ?? []).join(", ")}</td></tr>
              </tbody></table>) : <p className="na">NOT AVAILABLE. No forecast recorded for this ticker</p>}
            </section>
            <section className="panel"><h2>Data freshness</h2>
              {data.freshness.last_close_date ? <p>Last close {data.freshness.last_close_date}, usable from {timeET(data.freshness.usable_from)}, source {data.freshness.vendor}</p> : <p className="na">NOT AVAILABLE</p>}
              <h2>Order and risk check</h2>
              {data.proposal ? <p>{data.proposal.side.toUpperCase()} {data.proposal.quantity} for {data.proposal.session_date}, status {data.proposal.status.toUpperCase()}</p> : <p className="muted">No proposal</p>}
              {data.risk ? (<><p>Risk verdict {data.risk.verdict.toUpperCase()} at {timeET(data.risk.decided_at)}, {data.risk.checks_run.length} checks run</p>
                {data.risk.reasons.length > 0 && <ul>{data.risk.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}</>) : <p className="muted">No risk check recorded</p>}
            </section>
          </div>
          <div className="grid2">
            <section className="panel"><h2>Agreeing and opposing signals, Composite {data.composite.record_type?.toUpperCase() ?? ""}</h2>
              {data.composite.agreeing.length + data.composite.opposing.length === 0 && <p className="muted">None. No signal holds weight in the Composite, so none contributes to this ticker's score.</p>}
              <table><thead><tr><th>Signal</th><th>Direction</th><th className="num">Share of score</th></tr></thead><tbody>
                {data.composite.agreeing.map(([s, v]) => <tr key={s}><td>{s}</td><td className="gain">▲ agrees</td><td className="num">{v.toFixed(2)}</td></tr>)}
                {data.composite.opposing.map(([s, v]) => <tr key={s}><td>{s}</td><td className="loss">▼ opposes</td><td className="num">{v.toFixed(2)}</td></tr>)}
              </tbody></table>
              <h2 style={{ marginTop: 12 }}>Uncertainty</h2>
              <table><thead><tr><th>Signal</th><th className="num">Edge (% a year)</th><th className="num">P(edge above 0)</th></tr></thead><tbody>
                {data.composite.uncertainty.map((u) => <tr key={u.signal_id}><td>{u.signal_id}</td><td className="num">{(u.mu_hat * 100).toFixed(2)}</td><td className="num">{u.prob_positive.toFixed(2)}</td></tr>)}
              </tbody></table>
            </section>
            <section className="panel"><h2>Exclusions</h2>
              {data.composite.exclusions.map((x) => <div key={x.signal_id}><p>{x.signal_id}</p><ul>{x.reasons.map((r, i) => <li key={i} className="muted">{r}</li>)}</ul></div>)}
              <h2>News for this ticker</h2>
              {data.news.length === 0 ? <p className="muted">No linked stories</p> : <ul>{data.news.map((n, i) => <li key={i}>{timeET(n.usable_from)} {n.title}</li>)}</ul>}
            </section>
          </div>
        </>)}
    </>
  );
}
