import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { Term } from "../guide";

type Row = { signal_id: string; days: number | null; mean_annual: number | null; se_annual: number | null; sharpe: number | null; lower_90_double_cost: number | null; economic_pass: boolean | null; data_labels: string[] | null; record_type: string | null; summary: string };
type Data = { trial_count: number; method: string; holdout: string; rows: Row[] };

const p1 = (v: number | null) => (v === null ? "NOT AVAILABLE" : `${(v * 100).toFixed(1)}`);

export function BacktestsScreen({ tick }: { tick: number }) {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => { getJSON<Data>("/api/backtests").then(setData); }, [tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <section className="panel"><h2>Backtests</h2>
      <p className="muted">{data.method}.</p>
      <p className="muted">Holdout: {data.holdout}. <Term k="trial_count">Trials</Term> recorded: {data.trial_count}</p>
      {data.rows.length === 0 ? <p className="na">NOT AVAILABLE. No Composite run has recorded a backtest yet.</p> : (
        <table><thead><tr><th>Signal</th><th>Record</th><th>Data</th><th className="num">Days</th><th className="num">Net return (% a year)</th>
          <th className="num"><Term k="sharpe">Sharpe</Term></th><th className="num"><Term k="trial_count">Trials</Term></th>
          <th className="num">90% lower bound at double costs (% a year)</th><th>Result</th></tr></thead>
          <tbody>{data.rows.map((r) => (
            <tr key={r.signal_id} title={r.summary}><td>{r.signal_id}</td><td>{(r.record_type ?? "retrospective").toUpperCase()}</td>
              <td>{(r.data_labels ?? []).join(", ") || "NOT AVAILABLE"}</td><td className="num">{r.days ?? "NOT AVAILABLE"}</td>
              <td className="num">{p1(r.mean_annual)}</td><td className="num">{r.sharpe === null ? "NOT AVAILABLE" : r.sharpe.toFixed(2)}</td>
              <td className="num">{data.trial_count}</td><td className="num">{p1(r.lower_90_double_cost)}</td>
              <td>{r.economic_pass === null ? "NOT AVAILABLE" : r.economic_pass ? "PASS" : "FAIL"}</td></tr>))}
          </tbody></table>)}
    </section>
  );
}
