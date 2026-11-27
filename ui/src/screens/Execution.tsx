import { useEffect, useState, type ReactElement } from "react";
import { Execution, getJSON, OrderRow, post } from "../api";
import { modelName, plainReason } from "../labels";
import { sideLabel, timeET, usd } from "../format";

function Orders({ rows, actions }: { rows: OrderRow[]; actions?: (r: OrderRow) => ReactElement }) {
  if (rows.length === 0) return <p className="muted">None</p>;
  return (
    <table><thead><tr><th>Ticker</th><th>Side</th><th className="num">Shares</th><th className="num">Signal</th><th>Model</th><th>Status</th><th>Reason</th>{actions && <th>Action</th>}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.proposal_id}><td>{r.symbol}</td><td>{sideLabel(r.side)}</td><td className="num">{r.quantity}</td>
          <td className="num">{r.signal_strength === null ? "NOT AVAILABLE" : r.signal_strength.toFixed(2)}</td>
          <td className="muted">{modelName(r.model)}</td><td>{r.status.replace(/_/g, " ")}</td><td className="muted" title={plainReason(r.reason)}>{plainReason(r.reason.split("\n")[0])}</td>
          {actions && <td>{actions(r)}</td>}</tr>))}
      </tbody></table>
  );
}

export function ExecutionScreen({ tick, onChange }: { tick: number; onChange: () => void }) {
  const [data, setData] = useState<Execution | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getJSON<Execution>("/api/execution").then(setData).catch((e) => setErr(String(e))); }, [tick]);

  async function act(id: string, verb: "approve" | "reject") {
    const r = await post(`/api/proposals/${id}/${verb}`);
    if (!r.ok) setErr(`${verb} failed (${r.status})`);
    onChange();
  }
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <>
      <section className="panel"><h2>{data.venue} approval queue for {data.session_date ?? "NOT AVAILABLE"}</h2>
        <Orders rows={data.approval_queue} actions={(r) => (
          <span style={{ display: "flex", gap: 6 }}>
            <button onClick={() => act(r.proposal_id, "approve")}>Approve</button>
            <button className="danger" onClick={() => act(r.proposal_id, "reject")}>Reject</button>
          </span>)} />
      </section>
      <section className="panel"><h2>Orders</h2><Orders rows={data.orders} /></section>
      <div className="grid2">
        <section className="panel"><h2>Fills</h2>
          {data.fills.length === 0 ? <p className="muted">None</p> : (
            <table><thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th className="num">Shares</th><th className="num">Price (USD)</th><th className="num">Slippage (bps)</th><th>Venue</th></tr></thead>
              <tbody>{data.fills.map((f) => (
                <tr key={f.fill_id}><td>{timeET(f.filled_at)}</td><td>{f.symbol}</td><td>{sideLabel(f.side)}</td><td className="num">{f.quantity}</td>
                  <td className="num">{usd(f.price)}</td><td className="num">{f.slippage_bps === null ? "NOT AVAILABLE" : f.slippage_bps.toFixed(2)}</td><td>{f.venue}</td></tr>))}
              </tbody></table>)}
        </section>
        <section className="panel"><h2>Reconciliation</h2>
          <p className={data.reconciliation.status === "MISMATCH" ? "loss" : data.reconciliation.status === "MATCHED" ? "" : "na"}>{data.reconciliation.status}. {data.reconciliation.reason}</p>
          <h2>Slippage by window</h2>
          {data.execution_quality.length === 0 ? <p className="muted">No fills yet</p> : (
            <table><thead><tr><th>Window</th><th className="num">Fills</th><th className="num">Mean (bps)</th><th className="num">95% interval (bps)</th></tr></thead>
              <tbody>{data.execution_quality.map((w) => (
                <tr key={w.window}><td>{w.window}</td><td className="num">{w.fills}</td><td className="num">{w.mean_bps.toFixed(2)}</td>
                  <td className="num">{w.interval_95 ? `${w.interval_95[0].toFixed(2)} to ${w.interval_95[1].toFixed(2)}` : "NOT AVAILABLE"}</td></tr>))}
              </tbody></table>)}
          <p className="muted">{data.execution_quality_note}</p>
          <h2>Kill switch</h2><p>{data.kill_switch === null ? "NOT AVAILABLE. Risk service unreachable" : data.kill_switch ? "ON. New orders are blocked" : "OFF"}</p>
        </section>
      </div>
    </>
  );
}
