import { Fragment, useEffect, useState } from "react";
import { getJSON } from "../api";
import { Term } from "../guide";
import { Ticker } from "../stock";

type Row = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; expected_return: string; entry: string; model: string; tier: number | null; status: string; risk: string };
type Data = { session_date: string | null; venue: string; rows: Row[] };

export function OpportunitiesScreen({ tick, onReason }: { tick: number; onReason: (symbol: string) => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState<"signal" | "symbol">("signal");
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { getJSON<Data>("/api/opportunities").then(setData).catch((e) => setErr(String(e))); }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  if (!data.session_date) return <div className="panel na">NOT AVAILABLE. No decision run has proposed positions yet.</div>;
  const rows = [...data.rows].sort((a, b) => sort === "symbol" ? a.symbol.localeCompare(b.symbol) : Math.abs(b.signal_strength ?? 0) - Math.abs(a.signal_strength ?? 0));
  return (
    <section className="page">
      <div className="page-head"><h1>Proposed positions for {data.session_date}</h1></div>
      <p className="muted">Click a row to see the evidence. Click a ticker to see what the company is.</p>
      <div className="panel flush">
        <table className="rows"><thead><tr>
          <th><button className="th" onClick={() => setSort("symbol")}>Ticker{sort === "symbol" ? " ▼" : ""}</button></th><th>Action</th>
          <th className="num"><button className="th" onClick={() => setSort("signal")}><Term k="signal_strength">Signal</Term>{sort === "signal" ? " ▼" : ""}</button></th>
          <th><Term k="tier">Evidence tier</Term></th><th>Status</th></tr></thead>
          <tbody>{rows.map((r) => (
            <Fragment key={r.proposal_id}>
              <tr onClick={() => setOpen(open === r.proposal_id ? null : r.proposal_id)} className={open === r.proposal_id ? "selected clickable" : "clickable"} aria-expanded={open === r.proposal_id}>
                <td><Ticker symbol={r.symbol} /></td><td>{r.side === "buy" ? "▲ Buy" : "▼ Sell"} {r.quantity}</td>
                <td className="num">{r.signal_strength === null ? "NOT AVAILABLE" : r.signal_strength.toFixed(2)}</td>
                <td>{r.tier ?? "NOT AVAILABLE"}</td><td>{r.status}</td></tr>
              {open === r.proposal_id && (
                <tr className="detail"><td colSpan={5}>
                  <dl className="facts">
                    <dt>Model</dt><dd>{r.model}</dd>
                    <dt><Term k="alpha">Expected return</Term></dt><dd className="na">{r.expected_return}</dd>
                    <dt>Entry</dt><dd>{r.entry}</dd>
                    <dt>Risk result</dt><dd>{r.risk || "Checked again by the risk service at execution"}</dd>
                  </dl>
                  <button onClick={() => onReason(r.symbol)}>Open reasoning for {r.symbol}</button>
                </td></tr>)}
            </Fragment>))}
          </tbody></table>
      </div>
    </section>
  );
}
