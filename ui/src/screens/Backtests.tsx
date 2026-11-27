import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { dataLabel, signalName } from "../labels";
import { Tech } from "../stock";
import { Term } from "../guide";

type Row = { signal_id: string; days: number | null; mean_annual: number | null; se_annual: number | null; sharpe: number | null; lower_90_double_cost: number | null; economic_pass: boolean | null; data_labels: string[] | null; record_type: string | null; summary: string };
type Data = { trial_count: number; method: string; holdout: string; rows: Row[] };

const p1 = (v: number | null) => (v === null ? "NOT AVAILABLE" : `${(v * 100).toFixed(1)}`);

export function BacktestsScreen({ tick }: { tick: number }) {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => { getJSON<Data>("/api/backtests").then(setData); }, [tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <section className="page">
      <div className="page-head"><h1>Backtests</h1></div>
      <p className="muted">How each signal would have done in the past after trading costs. {data.trial_count} versions tested in total, which matters because testing many versions makes a lucky result more likely.</p>
      {data.rows.length === 0 ? <p className="na">Not available yet. No backtest has been recorded.</p> : (
        <div className="panel flush"><table><thead><tr><th>Signal</th><th>Data</th><th className="num">Days tested</th><th className="num">Return after costs (% a year)</th>
          <th className="num"><Term k="sharpe">Return per unit of risk</Term></th>
          <th className="num">Pessimistic case at double costs (% a year)</th><th>Worth trading after costs</th></tr></thead>
          <tbody>{data.rows.map((r) => (
            <tr key={r.signal_id}><td><strong>{signalName(r.signal_id)}</strong></td>
              <td>{(r.data_labels ?? []).map(dataLabel).join(", ") || "Not available"}</td><td className="num">{r.days ?? "Not available"}</td>
              <td className="num">{p1(r.mean_annual)}</td><td className="num">{r.sharpe === null ? "Not available" : r.sharpe.toFixed(2)}</td>
              <td className="num">{p1(r.lower_90_double_cost)}</td>
              <td>{r.economic_pass === null ? "Not available" : r.economic_pass ? "✓ Yes" : "No"}</td></tr>))}
          </tbody></table></div>)}
      <p className="muted small">Every result here is a back-test, so it can look better than real trading. Holdout period: {data.holdout.replace(/^NOT AVAILABLE\. /, "not available. ")}.</p>
      <Tech><p>{data.method}.</p>{data.rows.map((r) => <p key={r.signal_id}>{r.signal_id}: {r.summary}</p>)}</Tech>
    </section>
  );
}
