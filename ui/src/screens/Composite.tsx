import { Fragment, useEffect, useState } from "react";
import { getJSON } from "../api";
import { pct, timeET } from "../format";
import { Term } from "../guide";
import { familyName, plainReason, signalName, statusName } from "../labels";
import { Tech } from "../stock";

type Signal = { signal_id: string; family: string; tier: number; status: string; mu_hat: number; prob_positive: number; weight: number; capital_weight: number; eligible: boolean; reasons: string[]; claim: string | null; claim_id: string | null; data_labels: string[]; record_type: string; scores: { validity: string; predictive: string; economic: string } };
type Run = { status?: string; reason?: string; composite_run_id: string; as_of: string; record_type: string; data_labels: string[]; signals: Signal[]; unallocated_weight: number; calibration_status: string; calibration_reasons: string[]; optimizer_status: string; trial_count: number; frozen_weights: Record<string, number> };

export function CompositeScreen({ tick, onEvidence }: { tick: number; onEvidence: (claimId: string) => void }) {
  const [run, setRun] = useState<Run | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { getJSON<Run>("/api/composite").then(setRun); }, [tick]);
  if (!run) return <div className="panel muted">Loading</div>;
  if (run.status === "NOT AVAILABLE") return <div className="panel na">Not available yet. {run.reason}</div>;
  const trading = run.signals.filter((s) => s.capital_weight > 0);
  const demo = run.data_labels.includes("SYNTHETIC");
  return (
    <section className="page">
      <div className="page-head"><h1>How the signals combine</h1><span className="muted small">Updated {timeET(run.as_of)}</span></div>
      <section className="panel conclusion-panel">
        <p><strong>{trading.length === 0 ? "No signal has enough evidence to trade yet." : `${trading.length} of ${run.signals.length} signals carry trading weight.`}</strong>{" "}
          {trading.length === 0 ? "Each one is tracked and tested until it earns its place." : ""}</p>
        <p className="muted">{demo ? "These results come from demo data, so they are not evidence. " : ""}Results are back-tested, not recorded in advance. {run.trial_count} versions have been tested in total.</p>
      </section>
      <div className="panel flush">
        <table><thead><tr><th>Signal</th><th>Kind</th><th className="num"><Term k="tier">Evidence level</Term></th><th className="num">Expected edge (% a year)</th>
          <th className="num"><Term k="prob_positive">Chance the edge is real (%)</Term></th><th className="num">Trading weight (%)</th><th>Status</th></tr></thead>
          <tbody>{run.signals.map((s) => (
            <Fragment key={s.signal_id}>
              <tr className="clickable" tabIndex={0} onClick={() => setOpen(open === s.signal_id ? null : s.signal_id)}
                onKeyDown={(e) => { if (e.key === "Enter") setOpen(open === s.signal_id ? null : s.signal_id); }} aria-expanded={open === s.signal_id}>
                <td><strong>{signalName(s.signal_id)}</strong></td><td>{familyName(s.family)}</td><td className="num">{s.tier} of 6</td>
                <td className="num">{(s.mu_hat * 100).toFixed(1)}</td><td className="num">{(s.prob_positive * 100).toFixed(0)}</td>
                <td className="num">{pct(s.capital_weight, 1)}</td><td>{s.capital_weight > 0 ? "Trading" : "Not trading yet"}</td></tr>
              {open === s.signal_id && (
                <tr className="detail"><td colSpan={7}>
                  <dl className="facts">
                    <dt>Why not trading</dt><dd>{s.reasons.length === 0 ? "Eligible" : <ul className="plain">{s.reasons.map((r, i) => <li key={i}>{plainReason(r)}.</li>)}</ul>}</dd>
                    <dt>Published evidence</dt><dd>{plainReason(s.scores.validity)}</dd>
                    <dt>Forecast accuracy</dt><dd>{plainReason(s.scores.predictive)}</dd>
                    <dt>Value after costs</dt><dd>{plainReason(s.scores.economic)}</dd>
                  </dl>
                  {s.claim_id && <button onClick={() => onEvidence(s.claim_id!)}>See the research behind it</button>}
                  <Tech><p>Signal {s.signal_id}, family {s.family}, status {statusName(s.status)}, combined weight {pct(s.weight, 2)}%, claim {s.claim_id ?? "none"}.</p>
                    <p>Raw reasons: {s.reasons.join(" | ")}</p></Tech>
                </td></tr>)}
            </Fragment>))}
          </tbody></table>
      </div>
      <p className="muted small">Click a signal for its evidence and why it is or is not trading.</p>
      <Tech><p>Run {run.composite_run_id}. Calibration {run.calibration_status}. Optimizer {run.optimizer_status}. Unallocated weight {pct(run.unallocated_weight, 2)}%. Data labels {run.data_labels.join(", ")}. Frozen weights {JSON.stringify(run.frozen_weights)}.</p></Tech>
    </section>
  );
}
