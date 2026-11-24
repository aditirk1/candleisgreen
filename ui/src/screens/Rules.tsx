import { useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { timeET } from "../format";
import { Term } from "../guide";

type Limits = { effective: Record<string, unknown>; base: Record<string, unknown>; pending: Record<string, { value: number; confirmable_from: string; requested_at: string }>; editable: string[]; delay_hours: number } | null;
type Data = { chain_ok: boolean; records: { seq: number; time: string; actor: string; event: string; entity: string }[]; limits: Limits; parameters: { path: string; basis: string; label: string; note: string | null }[] };

export function RulesScreen({ tick, onChange }: { tick: number; onChange: () => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [basis, setBasis] = useState("all");
  useEffect(() => { getJSON<Data>("/api/audit").then(setData); }, [tick]);
  if (!data) return <div className="panel muted">Loading</div>;

  async function request(key: string) {
    const value = Number(edit[key]);
    const r = await post("/api/limits/request", { key, value });
    const body = await r.json().catch(() => ({}));
    setMsg(r.ok ? (body.status === "APPLIED" ? `${key} set to ${value}. Applied now` : `${key} change to ${value} waits until ${timeET(body.confirmable_from)} and needs confirmation`) : `Refused. ${body.detail ?? r.status}`);
    onChange();
  }
  async function confirm(key: string) {
    const r = await post("/api/limits/confirm", { key });
    const body = await r.json().catch(() => ({}));
    setMsg(r.ok ? `${key} loosening confirmed` : `Not confirmed. ${body.detail ?? r.status}`);
    onChange();
  }
  const L = data.limits;
  const params = data.parameters.filter((p) => basis === "all" || p.basis === basis);
  return (
    <>
      <section className="panel"><h2>Hard limits</h2>
        {!L ? <p className="loss">Risk service unreachable. Limits cannot be read or changed.</p> : (
          <>
            <p className="muted">A tighter value applies now. A looser value waits {L.delay_hours} hours and then needs a second confirmation. Only Aditi can change a limit.</p>
            <table><thead><tr><th>Limit</th><th className="num">Base</th><th className="num">Effective</th><th>Pending</th><th>New value</th><th></th></tr></thead>
              <tbody>{L.editable.map((k) => {
                const pend = L.pending[k];
                return (
                  <tr key={k}><td>{k}</td><td className="num">{String(L.base[k])}</td><td className="num">{String(L.effective[k])}</td>
                    <td>{pend ? `${pend.value} from ${timeET(pend.confirmable_from)}` : "None"}</td>
                    <td><input aria-label={`New value for ${k}`} className="field" value={edit[k] ?? ""} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} /></td>
                    <td><button onClick={() => request(k)} disabled={!edit[k]}>Request</button>{pend && <button onClick={() => confirm(k)}>Confirm</button>}</td></tr>);
              })}</tbody></table>
          </>)}
        {msg && <p role="status">{msg}</p>}
      </section>
      <div className="grid2">
        <section className="panel"><h2>Audit log</h2>
          <p className={data.chain_ok ? "gain" : "loss"}>{data.chain_ok ? "✓ Hash chain verified" : "✗ Hash chain broken"}</p>
          <div className="scroll"><table><thead><tr><th className="num">Seq</th><th>Time</th><th>Actor</th><th>Event</th><th>Entity</th></tr></thead>
            <tbody>{data.records.map((r) => (
              <tr key={r.seq}><td className="num">{r.seq}</td><td>{timeET(r.time)}</td><td>{r.actor}</td><td>{r.event}</td><td className="muted">{r.entity}</td></tr>))}
            </tbody></table></div>
        </section>
        <section className="panel"><h2>Parameters by <Term k="basis">basis</Term></h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            {["all", "empirical", "safeguard", "provisional", "external_fact"].map((b) => (
              <button key={b} className={basis === b ? "active" : ""} onClick={() => setBasis(b)}>{b.toUpperCase()}</button>))}
          </div>
          <div className="scroll"><table><thead><tr><th>Parameter</th><th>Basis</th></tr></thead>
            <tbody>{params.map((p) => (
              <tr key={p.path} title={[p.label, p.note].filter(Boolean).join("\n")}><td>{p.path}</td><td>{p.basis.toUpperCase()}</td></tr>))}
            </tbody></table></div>
        </section>
      </div>
    </>
  );
}
