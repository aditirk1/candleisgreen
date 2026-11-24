import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { timeET } from "../format";

type G = {
  sessions: { slot: string; utc: string; last_run: string | null; status: string; job: string }[];
  fx: { currency: string; series: string; date: string | null; usd_per_unit: number | null }[];
  momentum_by_market: { location: string; months: number; mean_monthly?: number; t_stat?: number; replicates?: boolean; status?: string; use?: string }[];
  entitlements: { capability: string; status: string; label: string }[];
  macro: { series: string; status: string; reason?: string; period?: string; value?: number | null; vintage?: number; known_from?: string; license?: string }[];
  markets: { mic: string; name: string; tag: string; hours_local?: string; settlement?: string; lot_size?: string; transaction_tax?: string; price_limits?: string; source?: string }[];
};

export function GlobalScreen({ tick }: { tick: number }) {
  const [g, setG] = useState<G | null>(null);
  useEffect(() => { getJSON<G>("/api/global").then(setG); }, [tick]);
  if (!g) return <div className="panel muted">Loading</div>;
  return (
    <>
      <div className="grid2">
        <section className="panel"><h2>Follow-the-sun jobs</h2>
          <table><thead><tr><th>Session</th><th>Time (UTC)</th><th>Job</th><th>Last run</th><th>Status</th></tr></thead>
            <tbody>{g.sessions.map((s) => <tr key={s.slot}><td>{s.slot.replace("_", " ")}</td><td>{s.utc}</td><td>{s.job}</td><td>{s.last_run ? timeET(s.last_run) : "NOT RUN"}</td><td>{s.status.toUpperCase()}</td></tr>)}</tbody></table>
        </section>
        <section className="panel"><h2>FX, FRED daily rates</h2>
          <table><thead><tr><th>Currency</th><th>Series</th><th>Date</th><th className="num">USD per unit</th></tr></thead>
            <tbody>{g.fx.map((r) => <tr key={r.currency}><td>{r.currency}</td><td className="muted">{r.series}</td><td>{r.date ?? "NOT AVAILABLE"}</td><td className="num">{r.usd_per_unit === null ? "NOT AVAILABLE" : r.usd_per_unit.toFixed(5)}</td></tr>)}</tbody></table>
        </section>
      </div>
      <section className="panel"><h2>Macro, as known now, every vintage kept (FRED API)</h2>
        {g.macro.length === 0 ? <p className="na">NOT AVAILABLE. Price database busy or no series configured</p> : (
          <table><thead><tr><th>Series</th><th>Period</th><th className="num">Value</th><th className="num">Revision</th><th>Known from</th><th>License</th></tr></thead>
            <tbody>{g.macro.map((m) => m.status !== "OK"
              ? <tr key={m.series}><td>{m.series}</td><td colSpan={5} className="na">NOT AVAILABLE. {m.reason}</td></tr>
              : <tr key={m.series}><td>{m.series}</td><td>{m.period}</td><td className="num">{m.value === null || m.value === undefined ? "NOT AVAILABLE" : m.value}</td>
                  <td className="num">{m.vintage}</td><td>{timeET(m.known_from)}</td><td className="muted">{m.license}</td></tr>)}
            </tbody></table>)}
      </section>
      <section className="panel"><h2>Momentum by market after 1993, research only (JKP, noncommercial license)</h2>
        {g.momentum_by_market.length === 0 ? <p className="na">NOT AVAILABLE. No global factor data loaded</p> : (
          <table><thead><tr><th>Market</th><th className="num">Months</th><th className="num">Mean (a month)</th><th className="num">t</th><th>Replicates</th><th>Use</th></tr></thead>
            <tbody>{g.momentum_by_market.map((m) => <tr key={m.location}><td>{m.location.toUpperCase()}</td><td className="num">{m.months}</td>
              <td className="num">{m.mean_monthly === undefined ? "NOT AVAILABLE" : (m.mean_monthly * 100).toFixed(2) + "%"}</td>
              <td className="num">{m.t_stat === undefined ? "NOT AVAILABLE" : m.t_stat.toFixed(2)}</td>
              <td className={m.replicates ? "gain" : "muted"}>{m.replicates === undefined ? m.status : m.replicates ? "▲ YES" : "NO"}</td><td className="muted">{m.use ?? "research only"}</td></tr>)}</tbody></table>)}
      </section>
      <div className="grid2">
        <section className="panel"><h2>Market rule table</h2>
          {g.markets.length === 0 ? <p className="na">NOT AVAILABLE</p> : (
            <table><thead><tr><th>Exchange</th><th>Tag</th><th>Hours (local)</th><th>Settlement</th><th>Lot</th><th>Tax on purchase</th></tr></thead>
              <tbody>{g.markets.map((m) => <tr key={m.mic} title={m.source}><td>{m.mic} {m.name}</td><td>{m.tag.toUpperCase()}</td><td>{m.hours_local ?? "NOT AVAILABLE"}</td><td>{m.settlement ?? "NOT AVAILABLE"}</td><td>{m.lot_size ?? "NOT AVAILABLE"}</td><td>{m.transaction_tax ?? "NOT AVAILABLE"}</td></tr>)}</tbody></table>)}
        </section>
        <section className="panel"><h2>Data entitlement map</h2>
          <table><thead><tr><th>Capability</th><th>Status</th></tr></thead>
            <tbody>{g.entitlements.map((e) => <tr key={e.capability} title={e.label}><td>{e.capability.replaceAll("_", " ")}</td><td className={e.status === "not_available" ? "loss" : ""}>{e.label}</td></tr>)}</tbody></table>
        </section>
      </div>
    </>
  );
}
