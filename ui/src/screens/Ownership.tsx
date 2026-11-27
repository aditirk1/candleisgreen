import { FormEvent, useEffect, useState } from "react";
import { getJSON } from "../api";
import { timeET, usd } from "../format";
import { Ticker } from "../stock";

type Insider = { accession: string; row_index: number; issuer_ticker: string | null; owner_name: string; role: string; plan_10b5_1: boolean; code: string | null; meaning: string;
  transaction_date: string | null; disclosed_at: string; disclosure_lag_days: number | null; shares: number | null; price: number | null; value_usd: number | null; acquired_disposed: string | null; url: string };
type Holding = { manager_name: string; manager_cik: string; period_end: string; disclosed_at: string; issuer_name: string; cusip: string; value_usd: number; shares: number; put_call: string; url: string };
type Large = { accession: string; form: string; filed: string | null; disclosed_at: string; url: string };
type Data = { insiders: Insider[]; holdings: Holding[]; holdings_total: number; large_holders: Large[]; sources: { module: string; status: string; label: string }[]; caveats: string[] };

const millions = (v: number) => (v / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 });

export function OwnershipScreen({ tick, ticker }: { tick: number; ticker?: string }) {
  const [sym, setSym] = useState(ticker ?? "");
  const [input, setInput] = useState(ticker ?? "");
  const [d, setD] = useState<Data | null>(null);
  useEffect(() => { getJSON<Data>(`/api/intelligence/ownership${sym ? `?symbol=${encodeURIComponent(sym)}` : ""}`).then(setD); }, [tick, sym]);
  const submit = (e: FormEvent) => { e.preventDefault(); setSym(input.trim().toUpperCase()); };
  if (!d) return <div className="panel muted">Loading</div>;
  const managers = Array.from(new Set(d.holdings.map((h) => h.manager_cik)));
  return (
    <section className="page">
      <form className="page-head" onSubmit={submit}>
        <h1>Insiders and institutions{sym ? `, ${sym}` : ""}</h1>
        <span><input aria-label="Filter by ticker" className="field" placeholder="Ticker" value={input} onChange={(e) => setInput(e.target.value)} /> <button type="submit">Filter</button></span>
      </form>
      <div className="data-banner none" role="note"><strong>RESEARCH ONLY.</strong> None of this feeds an order until a pre-registered test passes.</div>
      <section className="panel"><h2>Insider transactions, SEC Form 4</h2>
        {d.insiders.length === 0 ? <p className="muted">No Form 4 transactions recorded{sym ? ` for ${sym}` : ""}.</p> : (
          <div className="scroll"><table><thead><tr><th>Disclosed</th><th>Traded</th><th className="num">Lag (days)</th><th>Company</th><th>Insider</th><th>Type</th>
            <th className="num">Shares</th><th className="num">Price (USD)</th><th className="num">Value (USD millions)</th><th>Plan</th><th>Filing</th></tr></thead>
            <tbody>{d.insiders.map((r) => (
              <tr key={`${r.accession}-${r.row_index}`}><td>{timeET(r.disclosed_at)}</td><td>{r.transaction_date ?? "NOT AVAILABLE"}</td><td className="num">{r.disclosure_lag_days ?? ""}</td>
                <td>{r.issuer_ticker ? <Ticker symbol={r.issuer_ticker} /> : "NOT AVAILABLE"}</td><td>{r.owner_name}<br /><span className="muted small">{r.role}</span></td>
                <td className={r.code === "P" ? "gain" : r.code === "S" ? "loss" : ""}>{r.code === "P" ? "▲ " : r.code === "S" ? "▼ " : ""}{r.meaning}</td>
                <td className="num">{r.shares?.toLocaleString("en-US") ?? ""}</td><td className="num">{r.price === null ? "" : usd(r.price)}</td>
                <td className="num">{r.value_usd === null ? "" : millions(r.value_usd)}</td><td>{r.plan_10b5_1 ? "10b5-1 plan" : ""}</td>
                <td><a href={r.url} target="_blank" rel="noreferrer">{r.accession}</a></td></tr>))}
            </tbody></table></div>)}
      </section>
      <div className="grid2">
        <section className="panel"><h2>Institutional holdings, SEC Form 13F</h2>
          {d.holdings.length === 0 ? <p className="muted">No 13F filings recorded. Add manager CIKs to sources.sec.managers_13f.</p> : managers.map((m) => {
            const rows = d.holdings.filter((h) => h.manager_cik === m);
            return (
              <div key={m}>
                <p><strong>{rows[0].manager_name}</strong>. Holdings at quarter end {rows[0].period_end}, disclosed {timeET(rows[0].disclosed_at)}. <a href={rows[0].url} target="_blank" rel="noreferrer">Filing</a></p>
                <table><thead><tr><th>Issuer as filed</th><th>CUSIP</th><th className="num">Value (USD millions)</th><th className="num">Shares</th></tr></thead>
                  <tbody>{rows.slice(0, 15).map((h) => <tr key={h.cusip + h.put_call}><td>{h.issuer_name}{h.put_call ? ` (${h.put_call})` : ""}</td><td className="muted">{h.cusip}</td>
                    <td className="num">{millions(h.value_usd)}</td><td className="num">{h.shares.toLocaleString("en-US")}</td></tr>)}</tbody></table>
                {rows.length > 15 && <p className="muted small">Top 15 of {rows.length} positions by value.</p>}
              </div>);
          })}
        </section>
        <section className="panel"><h2>Large holder filings, Schedules 13D and 13G</h2>
          {d.large_holders.length === 0 ? <p className="muted">None recorded{sym ? ` for ${sym}` : ""}.</p> : (
            <ul className="plain list">{d.large_holders.map((l) => <li key={l.accession}><span>{l.form}</span> <span className="muted small">disclosed {timeET(l.disclosed_at)}</span> <a href={l.url} target="_blank" rel="noreferrer">Filing</a></li>)}</ul>)}
        </section>
      </div>
      <section className="panel"><h2>What these records are and are not</h2>
        <ul className="plain list">{d.caveats.map((c) => <li key={c}>{c}.</li>)}</ul>
      </section>
      <section className="panel"><h2>Sources and status</h2>
        <table><thead><tr><th>Module</th><th>Status</th></tr></thead>
          <tbody>{d.sources.map((s) => <tr key={s.module}><td>{s.module.replace(/_/g, " ")}</td><td className={s.status === "not_available" ? "na" : ""}>{s.label}</td></tr>)}</tbody></table>
      </section>
    </section>
  );
}
