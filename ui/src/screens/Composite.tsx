import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { pct, timeET } from "../format";

type Signal = { signal_id: string; family: string; tier: number; status: string; mu_hat: number; prob_positive: number; weight: number; capital_weight: number; eligible: boolean; reasons: string[]; claim: string | null; claim_id: string | null; data_labels: string[]; record_type: string; scores: { validity: string; predictive: string; economic: string } };
type Run = { status?: string; reason?: string; composite_run_id: string; as_of: string; record_type: string; data_labels: string[]; signals: Signal[]; unallocated_weight: number; calibration_status: string; calibration_reasons: string[]; optimizer_status: string; trial_count: number; frozen_weights: Record<string, number> };

export function CompositeScreen({ tick, onEvidence }: { tick: number; onEvidence: (claimId: string) => void }) {
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => { getJSON<Run>("/api/composite").then(setRun); }, [tick]);
  if (!run) return <div className="panel muted">Loading</div>;
  if (run.status === "NOT AVAILABLE") return <div className="panel na">NOT AVAILABLE. {run.reason}</div>;
  return (
    <>
      <section className="panel"><h2>Composite run {run.composite_run_id}</h2>
        <p>As of {timeET(run.as_of)}. Record {run.record_type.toUpperCase()}. Data {run.data_labels.join(", ")}. Calibration {run.calibration_status.toUpperCase()}. Optimizer {run.optimizer_status.toUpperCase()}.</p>
        <p className="muted">Unallocated weight {pct(run.unallocated_weight)}%. Variants tried across the registry {run.trial_count}. Frozen benchmark weights {Object.keys(run.frozen_weights).length === 0 ? "NOT AVAILABLE, no signal has held capital yet" : JSON.stringify(run.frozen_weights)}.</p>
      </section>
      <section className="panel"><h2>Signals</h2>
        <table><thead><tr><th>Signal</th><th>Family</th><th className="num">Tier</th><th className="num">Edge (% a year)</th><th className="num">P(edge above 0)</th><th className="num">Weight (%)</th><th className="num">Capital weight (%)</th><th>Eligible</th><th>Evidence</th></tr></thead>
          <tbody>{run.signals.map((s) => (
            <tr key={s.signal_id}><td>{s.signal_id}</td><td>{s.family}</td><td className="num">{s.tier}</td><td className="num">{(s.mu_hat * 100).toFixed(2)}</td>
              <td className="num">{s.prob_positive.toFixed(2)}</td><td className="num">{pct(s.weight)}</td><td className="num">{pct(s.capital_weight)}</td>
              <td>{s.eligible ? "YES" : "NO"}</td>
              <td>{s.claim_id ? <button onClick={() => onEvidence(s.claim_id!)}>Evidence chain</button> : <span className="na">NOT AVAILABLE</span>}</td></tr>))}
          </tbody></table>
      </section>
      {run.signals.map((s) => (
        <section className="panel" key={s.signal_id}><h2>{s.signal_id}, the three scores</h2>
          <table><tbody>
            <tr><td>Validity</td><td>{s.scores.validity}</td></tr>
            <tr><td>Predictive accuracy</td><td>{s.scores.predictive}</td></tr>
            <tr><td>Economic value</td><td>{s.scores.economic}</td></tr>
          </tbody></table>
          <h2 style={{ marginTop: 12 }}>Why it is not trading</h2>
          {s.reasons.length === 0 ? <p className="muted">Eligible</p> : <ul>{s.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
        </section>))}
    </>
  );
}
