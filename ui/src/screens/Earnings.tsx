import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { pct, signed, timeET } from "../format";

type Row = { period_end: string; eps_diluted: number; eps_yoy_change: number | null; revenue: number | null; revenue_yoy_pct: number | null; filed_at: string; source: string; vs_consensus: string };
type Data = { status: string; reason?: string; issuers: { cik: string; instrument_id: string; ticker: string | null; industry: string }[]; instrument_id?: string; rows: Row[]; consensus?: string };

export function EarningsScreen({ tick }: { tick: number }) {
  const [sel, setSel] = useState<string | null>(null);
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getJSON<Data>(`/api/earnings${sel ? `?instrument_id=${encodeURIComponent(sel)}` : ""}`).then(setData).catch((e) => setErr(String(e)));
  }, [tick, sel]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  if (data.status !== "OK") return <div className="panel na">{data.status}. {data.reason}</div>;
  return (
    <>
      <section className="panel"><h2>Issuers with SEC filings</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {data.issuers.map((i) => (
            <button key={i.instrument_id} className={i.instrument_id === data.instrument_id ? "active" : ""} onClick={() => setSel(i.instrument_id)}>
              {i.ticker ?? i.cik} ({i.industry})
            </button>))}
        </div>
      </section>
      <section className="panel"><h2>Scorecard, as reported in SEC filings</h2>
        <p className="muted">Compared with consensus: {data.consensus}</p>
        {data.rows.length === 0 ? <p className="muted">No quarterly figures</p> : (
          <table><thead><tr><th>Quarter end</th><th className="num">Diluted EPS (USD)</th><th className="num">EPS change on a year ago (USD)</th>
            <th className="num">Revenue (USD millions)</th><th className="num">Revenue change on a year ago (%)</th><th>Filed</th><th>Filing</th></tr></thead>
            <tbody>{data.rows.map((r) => {
              const e = signed(r.eps_yoy_change, (x) => x.toFixed(2));
              const v = signed(r.revenue_yoy_pct, (x) => pct(x, 1));
              const accn = r.source.split(" ")[0];
              const url = r.source.split(" ").slice(2).join(" ");
              return (
                <tr key={r.period_end}><td>{r.period_end}</td><td className="num">{r.eps_diluted.toFixed(2)}</td>
                  <td className={`num ${e.cls}`}>{e.text}</td><td className="num">{r.revenue === null ? "NOT AVAILABLE" : (r.revenue / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>
                  <td className={`num ${v.cls}`}>{v.text}</td><td>{timeET(r.filed_at)}</td><td><a href={url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{accn}</a></td></tr>);
            })}</tbody></table>)}
      </section>
    </>
  );
}
