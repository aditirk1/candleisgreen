import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { Term } from "../guide";

type Row = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; expected_return: string; entry: string; model: string; tier: number | null; status: string; risk: string };
type Data = { session_date: string | null; venue: string; rows: Row[] };

export function OpportunitiesScreen({ tick, onReason }: { tick: number; onReason: (symbol: string) => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState<"signal" | "symbol">("signal");
  const [sel, setSel] = useState<Row | null>(null);
  useEffect(() => { getJSON<Data>("/api/opportunities").then(setData).catch((e) => setErr(String(e))); }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  if (!data.session_date) return <div className="panel na">NOT AVAILABLE. No decision run has proposed positions yet.</div>;
  const rows = [...data.rows].sort((a, b) => sort === "symbol" ? a.symbol.localeCompare(b.symbol) : Math.abs(b.signal_strength ?? 0) - Math.abs(a.signal_strength ?? 0));
  const cur = sel ?? rows[0] ?? null;
  return (
    <div className="grid2">
      <section className="panel"><h2>Proposed positions for {data.session_date}</h2>
        <table><thead><tr>
          <th><button onClick={() => setSort("symbol")} className={sort === "symbol" ? "active" : ""}>Ticker</button></th><th>Side</th><th className="num">Shares</th>
          <th className="num"><button onClick={() => setSort("signal")} className={sort === "signal" ? "active" : ""}><Term k="signal_strength">Signal</Term></button></th>
          <th><Term k="tier">Tier</Term></th><th>Status</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.proposal_id} onClick={() => setSel(r)} style={{ cursor: "pointer" }} className={cur?.proposal_id === r.proposal_id ? "selected" : ""}>
              <td>{r.symbol}</td><td>{r.side === "buy" ? "▲ BUY" : "▼ SELL"}</td><td className="num">{r.quantity}</td>
              <td className="num">{r.signal_strength === null ? "NOT AVAILABLE" : r.signal_strength.toFixed(3)}</td>
              <td>{r.tier ?? "NOT AVAILABLE"}</td><td>{r.status.toUpperCase()}</td></tr>))}
          </tbody></table>
      </section>
      <section className="panel"><h2>Evidence</h2>
        {!cur ? <p className="muted">No proposal selected</p> : (
          <dl className="facts">
            <dt>Ticker</dt><dd>{cur.symbol}</dd>
            <dt>Model</dt><dd>{cur.model}</dd>
            <dt><Term k="alpha">Expected return</Term></dt><dd className="na">{cur.expected_return}</dd>
            <dt>Entry</dt><dd>{cur.entry}</dd>
            <dt>Validation</dt><dd>Tier {cur.tier ?? "NOT AVAILABLE"}</dd>
            <dt>Risk result</dt><dd>{cur.risk || "Checked again by the risk service at execution"}</dd>
            <dd><button onClick={() => onReason(cur.symbol)}>Open reasoning for {cur.symbol}</button></dd>
          </dl>)}
      </section>
    </div>
  );
}
