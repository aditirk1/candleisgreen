import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { capabilityName, humanize, licenseName, plainReason, tagName } from "../labels";
import { useMode } from "../theme";
const SLOTS: Record<string, string> = { asia_pacific: "Asia Pacific", europe: "Europe", us: "United States", overnight_review: "Overnight review" };
const CURRENCIES: Record<string, string> = { EUR: "Euro (EUR)", GBP: "British pound (GBP)", JPY: "Japanese yen (JPY)", HKD: "Hong Kong dollar (HKD)", CNY: "Chinese yuan (CNY)", CAD: "Canadian dollar (CAD)" };
const SERIES: Record<string, string> = { CPIAUCSL: "Consumer prices (CPI)", UNRATE: "Unemployment rate", PAYEMS: "Jobs, nonfarm payrolls", GDPC1: "Economic output (real GDP)", FEDFUNDS: "Federal funds rate", DGS10: "10-year Treasury yield" };
const seriesName = (id: string, adv: boolean) => `${SERIES[id] ?? id}${adv && SERIES[id] ? ` (${id})` : ""}`;
const JOBS: Record<string, string> = { global_factors: "Global factor data", fx: "Exchange rates and macro data", record: "Daily price recording", review: "Research review", preopen: "Pre-open check", execute: "Order execution", expire: "Expire unapproved orders", decide: "Next-day decision" };
const COUNTRIES: Record<string, string> = { USA: "United States", GBR: "United Kingdom", DEU: "Germany", JPN: "Japan", HKG: "Hong Kong", FRA: "France", CHN: "China", CAN: "Canada" };
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
  const adv = useMode() === "advanced";
  const [g, setG] = useState<G | null>(null);
  useEffect(() => { getJSON<G>("/api/global").then(setG); }, [tick]);
  if (!g) return <div className="panel muted">Loading</div>;
  return (
    <>
      <div className="grid2">
        <section className="panel"><h2>Scheduled jobs through the day</h2>
          <table><thead><tr><th>Market hours</th><th>Time (UTC)</th><th>Job</th><th>Last run</th><th>Status</th></tr></thead>
            <tbody>{g.sessions.map((s) => <tr key={s.slot}><td>{SLOTS[s.slot] ?? humanize(s.slot)}</td><td>{s.utc}</td><td>{JOBS[s.job] ?? humanize(s.job)}</td><td>{s.last_run ? timeET(s.last_run) : "Not run yet"}</td><td>{s.status === "ok" || s.status === "OK" ? "✓ OK" : humanize(s.status)}</td></tr>)}</tbody></table>
        </section>
        <section className="panel"><h2>Exchange rates, daily</h2>
          <table><thead><tr><th>Currency</th>{adv && <th>Series</th>}<th>Date</th><th className="num">USD per unit</th></tr></thead>
            <tbody>{g.fx.map((r) => <tr key={r.currency}><td>{CURRENCIES[r.currency] ?? r.currency}</td>{adv && <td className="muted">{r.series}</td>}<td>{r.date ?? "NOT AVAILABLE"}</td><td className="num">{r.usd_per_unit === null ? "NOT AVAILABLE" : r.usd_per_unit.toFixed(5)}</td></tr>)}</tbody></table>
        </section>
      </div>
      <section className="panel"><h2>Economic data, as first published and every revision since</h2>
        {g.macro.length === 0 ? <p className="na">NOT AVAILABLE. Price database busy or no series configured</p> : (
          <table><thead><tr><th>Measure</th><th>Period</th><th className="num">Value</th><th className="num">Revision</th><th>Known from</th><th>Terms</th></tr></thead>
            <tbody>{g.macro.map((m) => m.status !== "OK"
              ? <tr key={m.series}><td>{seriesName(m.series, adv)}</td><td colSpan={5} className="na">NOT AVAILABLE. {plainReason(m.reason)}</td></tr>
              : <tr key={m.series}><td>{seriesName(m.series, adv)}</td><td>{m.period}</td><td className="num">{m.value === null || m.value === undefined ? "NOT AVAILABLE" : m.value}</td>
                  <td className="num">{m.vintage}</td><td>{timeET(m.known_from)}</td><td className="muted">{licenseName(m.license)}</td></tr>)}
            </tbody></table>)}
      </section>
      <section className="panel"><h2>Momentum in other countries since 1993, research only</h2>
        {g.momentum_by_market.length === 0 ? <p className="na">NOT AVAILABLE. No global factor data loaded</p> : (
          <table><thead><tr><th>Market</th><th className="num">Months</th><th className="num">Average return (a month)</th><th className="num">t-statistic</th><th>Held up</th><th>Use</th></tr></thead>
            <tbody>{g.momentum_by_market.map((m) => <tr key={m.location}><td>{COUNTRIES[m.location.toUpperCase()] ?? m.location.toUpperCase()}</td><td className="num">{m.months}</td>
              <td className="num">{m.mean_monthly === undefined ? "NOT AVAILABLE" : (m.mean_monthly * 100).toFixed(2) + "%"}</td>
              <td className="num">{m.t_stat === undefined ? "NOT AVAILABLE" : m.t_stat.toFixed(2)}</td>
              <td className={m.replicates ? "gain" : "muted"}>{m.replicates === undefined ? m.status : m.replicates ? "▲ Yes" : "No"}</td><td className="muted">{m.use ?? "research only"}</td></tr>)}</tbody></table>)}
      </section>
      <div className="grid2">
        <section className="panel"><h2>Trading rules by exchange</h2>
          {g.markets.length === 0 ? <p className="na">NOT AVAILABLE</p> : (
            <table><thead><tr><th>Exchange</th><th>Here</th><th>Hours (local)</th><th>Settlement</th><th>Minimum lot</th><th>Tax on purchase</th></tr></thead>
              <tbody>{g.markets.map((m) => <tr key={m.mic} title={m.source}><td>{m.name}</td><td>{tagName(m.tag)}</td><td>{m.hours_local ?? "NOT AVAILABLE"}</td><td>{m.settlement ?? "NOT AVAILABLE"}</td><td>{m.lot_size ?? "NOT AVAILABLE"}</td><td>{m.transaction_tax ?? "NOT AVAILABLE"}</td></tr>)}</tbody></table>)}
        </section>
        <section className="panel"><h2>What data the system can use</h2>
          <table><thead><tr><th>Data</th><th>Status</th></tr></thead>
            <tbody>{g.entitlements.map((e) => <tr key={e.capability} title={e.label}><td>{capabilityName(e.capability)}</td><td className={e.status === "not_available" ? "loss" : ""}>{plainReason(e.label)}</td></tr>)}</tbody></table>
        </section>
      </div>
    </>
  );
}
