import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { timeET } from "../format";

type Experiment = { experiment_id: string; claim_id: string; study_type: string; status: string; plan: Record<string, unknown>; result: Record<string, unknown> | null; registered_at: string; completed_at: string | null; variants: number; selection_note: string };
type Claim = { claim_id: string; status: string; signal_id: string | null; tier: number | null; card: { title: string; reported_effect?: { monthly_return_pct: number; t_stat: number; sample: number[] }; replication_quality_in_source?: string } };
type Overview = { claims: Claim[]; experiments: Experiment[]; failures: Experiment[]; trial_count: number };
type Chain = { claim: Claim; experiments: Experiment[]; links: { from_id: string; to_id: string; relation: string; independence: string }[] };

function ExperimentRow({ e }: { e: Experiment }) {
  const r = (e.result ?? {}) as Record<string, unknown>;
  return (
    <tr>
      <td>{e.study_type}</td><td className={e.status === "FAILED" ? "loss" : e.status === "PASSED" ? "gain" : ""}>{e.status === "FAILED" ? "▼ FAILED" : e.status === "PASSED" ? "▲ PASSED" : e.status}</td>
      <td className="num">{String(r.mean_monthly_pct ?? "NOT AVAILABLE")}</td><td className="num">{String(r.t_stat ?? "NOT AVAILABLE")}</td>
      <td className="num">{String(r.months ?? "")}</td><td className="muted">{String(e.plan.rule ?? "")}</td><td className="num">{e.variants}</td>
      <td>{timeET(e.registered_at)}</td>
    </tr>
  );
}

const EXP_HEAD = <thead><tr><th>Study</th><th>Result</th><th className="num">Mean (% a month)</th><th className="num">t</th><th className="num">Months</th><th>Pre-registered rule</th><th className="num">Variants</th><th>Registered</th></tr></thead>;

export function ResearchScreen({ tick, focus }: { tick: number; focus: string | null }) {
  const [data, setData] = useState<Overview | null>(null);
  const [chain, setChain] = useState<Chain | null>(null);
  const [sel, setSel] = useState<string | null>(focus);
  useEffect(() => { getJSON<Overview>("/api/research").then(setData); }, [tick]);
  useEffect(() => { if (focus) setSel(focus); }, [focus]);
  useEffect(() => { if (sel) getJSON<Chain>(`/api/research/chain/${sel}`).then(setChain); else setChain(null); }, [sel, tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <>
      <section className="panel"><h2>Claim cards ({data.trial_count} variants tried in total)</h2>
        <table><thead><tr><th>Claim</th><th>Status</th><th className="num">Paper (% a month)</th><th className="num">Paper t</th><th>Sample</th><th>Signal</th><th className="num">Tier</th><th>Evidence</th></tr></thead>
          <tbody>{data.claims.map((c) => (
            <tr key={c.claim_id}><td>{c.card.title}</td><td className={c.status === "FAILED" ? "loss" : ""}>{c.status}</td>
              <td className="num">{c.card.reported_effect?.monthly_return_pct ?? "NOT AVAILABLE"}</td><td className="num">{c.card.reported_effect?.t_stat ?? "NOT AVAILABLE"}</td>
              <td>{c.card.reported_effect ? `${c.card.reported_effect.sample[0]} to ${c.card.reported_effect.sample[1]}` : ""}</td>
              <td className="muted">{c.signal_id ?? ""}</td><td className="num">{c.tier ?? ""}</td>
              <td><button className={sel === c.claim_id ? "active" : ""} onClick={() => setSel(c.claim_id)}>Evidence chain</button></td></tr>))}
          </tbody></table>
      </section>
      {chain && (
        <section className="panel"><h2>Evidence chain: {chain.claim.card.title}</h2>
          <p className="muted">Claim {chain.claim.claim_id}. Status {chain.claim.status}. Source replication quality {chain.claim.card.replication_quality_in_source ?? "NOT AVAILABLE"}.</p>
          <table>{EXP_HEAD}<tbody>{chain.experiments.map((e) => <ExperimentRow key={e.experiment_id} e={e} />)}</tbody></table>
          <h2 style={{ marginTop: 12 }}>Links</h2>
          <table><thead><tr><th>From</th><th>Relation</th><th>To</th><th>Independence</th></tr></thead>
            <tbody>{chain.links.map((l, i) => <tr key={i}><td className="muted">{l.from_id}</td><td>{l.relation}</td><td className="muted">{l.to_id}</td><td>{l.independence}</td></tr>)}</tbody></table>
          {chain.experiments.filter((e) => e.selection_note).map((e) => <p key={e.experiment_id} className="muted">Selection note: {e.selection_note}</p>)}
        </section>)}
      <section className="panel"><h2>Failure archive</h2>
        {data.failures.length === 0 ? <p className="muted">No failed experiments</p> : (
          <table>{EXP_HEAD}<tbody>{data.failures.map((e) => <ExperimentRow key={e.experiment_id} e={e} />)}</tbody></table>)}
      </section>
    </>
  );
}
