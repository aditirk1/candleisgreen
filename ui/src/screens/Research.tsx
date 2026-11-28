import { useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { timeET } from "../format";
import { dataLabel, humanize, plainReason, signalName, statusName, studyName } from "../labels";
import { Tech } from "../stock";
import { InboxPanel } from "./Inbox";

type Experiment = { experiment_id: string; claim_id: string; study_type: string; status: string; plan: Record<string, unknown>; result: Record<string, unknown> | null; registered_at: string; completed_at: string | null; variants: number; selection_note: string };
type Claim = { claim_id: string; status: string; signal_id: string | null; tier: number | null; card: { title: string; reported_effect?: { monthly_return_pct: number; t_stat: number; sample: number[] }; replication_quality_in_source?: string } };
type Digest = { date: string; new_hypotheses: unknown[]; duplicates: unknown[]; needs_data: { claim_id: string; missing: string[]; free_substitute: Record<string, string> }[]; results: unknown[]; contradictions: { claim_id: string; signal_id: string }[]; reevaluations_opened: string[]; queued: string[] };
type Overview = { claims: Claim[]; experiments: Experiment[]; failures: Experiment[]; trial_count: number; digests: Digest[];
  reevaluations: { case_id: string; signal_id: string; trigger_claim_id: string; opened_at: string; status: string; result: Record<string, unknown> | null }[];
  promotions: { proposal_id: string; signal_id: string; to_tier: number; proposed_at: string; status: string; decided_by: string | null }[];
  models: { experiment_id: string; champion: string; challenger: string; result: { test: string; pvalue: number; subperiods_held: number; recommendation: string; data_labels: string[] } }[] };
type Chain = { claim: Claim; experiments: Experiment[]; links: { from_id: string; to_id: string; relation: string; independence: string }[] };

function ExperimentRow({ e }: { e: Experiment }) {
  const r = (e.result ?? {}) as Record<string, unknown>;
  return (
    <tr>
      <td>{studyName(e.study_type)}</td><td className={e.status === "FAILED" ? "loss" : e.status === "PASSED" ? "gain" : ""}>{e.status === "FAILED" ? "▼ Did not hold up" : e.status === "PASSED" ? "▲ Held up" : statusName(e.status)}</td>
      <td className="num">{typeof r.mean_monthly_pct === "number" ? (r.mean_monthly_pct as number).toFixed(2) : "Not available"}</td><td className="num">{typeof r.t_stat === "number" ? (r.t_stat as number).toFixed(1) : "Not available"}</td>
      <td className="num">{String(r.months ?? "")}</td><td className="muted">{plainReason(String(e.plan.rule ?? ""))}</td><td className="num">{e.variants}</td>
      <td>{timeET(e.registered_at)}</td>
    </tr>
  );
}

const EXP_HEAD = <thead><tr><th>Test</th><th>Result</th><th className="num">Average return (% a month)</th><th className="num">t-statistic</th><th className="num">Months</th><th>Pass rule, set before testing</th><th className="num">Versions tried</th><th>Registered</th></tr></thead>;

const RESEARCH_TABS: [string, string][] = [["digest", "Today"], ["claims", "Research ideas"], ["inbox", "Capture inbox"]];

export function ResearchScreen({ tick, focus }: { tick: number; focus: string | null }) {
  const [tab, setTab] = useState(focus ? "claims" : "digest");
  const [data, setData] = useState<Overview | null>(null);
  const [chain, setChain] = useState<Chain | null>(null);
  const [sel, setSel] = useState<string | null>(focus);
  useEffect(() => { getJSON<Overview>("/api/research").then(setData); }, [tick]);
  useEffect(() => { if (focus) setSel(focus); }, [focus]);
  useEffect(() => { if (sel) getJSON<Chain>(`/api/research/chain/${sel}`).then(setChain); else setChain(null); }, [sel, tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  const d = data.digests[0];
  async function decide(id: string, verb: "approve" | "decline") { await post(`/api/promotions/${id}/${verb}`); getJSON<Overview>("/api/research").then(setData); }
  return (
    <div className="page">
      <div className="page-head"><h1>Research</h1>
        <div className="segmented" role="group" aria-label="Research sections">
          {RESEARCH_TABS.map(([k, label]) => <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>)}
        </div>
      </div>
      {tab === "inbox" && <>
      <InboxPanel tick={tick} />
      </>}
      {tab === "digest" && <>
      <div className="grid2">
        <section className="panel"><h2>Daily research digest {d ? d.date : ""}</h2>
          {!d ? <p className="muted">No digest yet</p> : (<table><tbody>
            <tr><td>New ideas registered for testing</td><td className="num">{d.new_hypotheses.length}</td></tr>
            <tr><td>Repeats of earlier ideas</td><td className="num">{d.duplicates.length}</td></tr>
            <tr><td>Test results</td><td className="num">{d.results.length}</td></tr>
            <tr><td>New research against a signal in use</td><td className="num">{d.contradictions.length}</td></tr>
            <tr><td>Signal reviews opened</td><td className="num">{d.reevaluations_opened.length}</td></tr>
            <tr><td>Waiting for data</td><td className="num">{d.needs_data.length}</td></tr>
          </tbody></table>)}
          {d && d.needs_data.map((n) => <p key={n.claim_id} className="muted">Needs data: {n.missing.join(", ")}. Free substitute: {Object.values(n.free_substitute).join(", ")}</p>)}
        </section>
        <section className="panel"><h2>Signals under review</h2>
          {data.reevaluations.length === 0 ? <p className="muted">None</p> : (
            <table><thead><tr><th>Signal</th><th>Opened</th><th>Status</th></tr></thead>
              <tbody>{data.reevaluations.map((c) => <tr key={c.case_id}><td>{signalName(c.signal_id)}</td><td>{timeET(c.opened_at)}</td><td>{statusName(c.status)}</td></tr>)}</tbody></table>)}
          <p className="muted small">A review opens when new research contradicts a signal in use.</p>
          <h2 style={{ marginTop: 12 }}>Waiting for your decision</h2>
          {data.promotions.length === 0 ? <p className="muted">None</p> : (
            <table><thead><tr><th>Signal</th><th className="num">Move to evidence level</th><th>Status</th><th>Decision</th></tr></thead>
              <tbody>{data.promotions.map((p) => <tr key={p.proposal_id}><td>{signalName(p.signal_id)}</td><td className="num">{p.to_tier}</td><td>{statusName(p.status)}</td>
                <td>{p.status === "PENDING" ? <span style={{ display: "flex", gap: 6 }}><button onClick={() => decide(p.proposal_id, "approve")}>Approve</button><button className="danger" onClick={() => decide(p.proposal_id, "decline")}>Decline</button></span> : p.decided_by === "user:aditi" ? "You" : p.decided_by}</td></tr>)}</tbody></table>)}
        </section>
      </div>
      <section className="panel"><h2>Model comparisons, current model against a challenger</h2>
        {data.models.length === 0 ? <p className="muted">No comparisons yet</p> : (
          <table><thead><tr><th>Current model</th><th>Challenger</th><th>How compared</th><th className="num">Chance it is luck</th><th className="num">Periods it held in</th><th>Data</th><th>Result</th></tr></thead>
            <tbody>{data.models.map((m) => <tr key={m.experiment_id}><td>{signalName(m.champion)}</td><td>{signalName(m.challenger)}</td><td className="muted">{m.result.test}</td>
              <td className="num">{m.result.pvalue.toFixed(3)}</td><td className="num">{m.result.subperiods_held} of 3</td><td>{m.result.data_labels.map(dataLabel).join(", ")}</td><td>{m.result.recommendation.charAt(0).toUpperCase() + m.result.recommendation.slice(1)}</td></tr>)}</tbody></table>)}
      </section>
      </>}
      {tab === "claims" && <>
      <section className="panel"><h2>Research ideas ({data.trial_count} versions tested in total)</h2>
        <table><thead><tr><th>Idea</th><th>Status</th><th className="num">Published return (% a month)</th><th className="num">Published t-statistic</th><th>Years studied</th><th>Used by</th><th className="num">Evidence level</th><th></th></tr></thead>
          <tbody>{data.claims.map((c) => (
            <tr key={c.claim_id}><td>{c.card.title}</td><td className={c.status === "FAILED" ? "loss" : ""}>{statusName(c.status)}</td>
              <td className="num">{c.card.reported_effect?.monthly_return_pct ?? "Not available"}</td><td className="num">{c.card.reported_effect?.t_stat ?? "Not available"}</td>
              <td>{c.card.reported_effect ? `${c.card.reported_effect.sample[0]} to ${c.card.reported_effect.sample[1]}` : ""}</td>
              <td className="muted">{c.signal_id ? signalName(c.signal_id) : ""}</td><td className="num">{c.tier ?? ""}</td>
              <td><button className={sel === c.claim_id ? "active" : ""} onClick={() => setSel(c.claim_id)}>Show evidence</button></td></tr>))}
          </tbody></table>
      </section>
      {chain && (
        <section className="panel"><h2>Evidence: {chain.claim.card.title}</h2>
          <p className="muted">Status {statusName(chain.claim.status)}. How well the data source reproduced it: {humanize((chain.claim.card.replication_quality_in_source ?? "not stated").replace(/^\d_/, ""))}.</p>
          <table>{EXP_HEAD}<tbody>{chain.experiments.map((e) => <ExperimentRow key={e.experiment_id} e={e} />)}</tbody></table>
          {chain.links.length > 0 && <p className="muted small">{chain.links.length} related research {chain.links.length === 1 ? "item" : "items"}: {Array.from(new Set(chain.links.map((l) => l.relation))).join(", ")}.</p>}
          {chain.experiments.filter((e) => e.selection_note).map((e) => <p key={e.experiment_id} className="muted">Note: {e.selection_note}</p>)}
          <Tech><p>Claim {chain.claim.claim_id}.</p>{chain.links.map((l, i) => <p key={i}>{l.from_id} {l.relation} {l.to_id} ({l.independence})</p>)}</Tech>
        </section>)}
      <section className="panel"><h2>Failure archive, ideas that did not hold up</h2>
        {data.failures.length === 0 ? <p className="muted">No failed tests</p> : (
          <table>{EXP_HEAD}<tbody>{data.failures.map((e) => <ExperimentRow key={e.experiment_id} e={e} />)}</tbody></table>)}
      </section>
      </>}
    </div>
  );
}
