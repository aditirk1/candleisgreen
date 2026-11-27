import { FormEvent, useEffect, useState } from "react";
import { getJSON } from "../api";
import { Bar, PriceChart } from "../chart";
import { sideLabel, timeET } from "../format";

type Metric = { label: string; status: string; value: number | null; unit: string; period?: string; source?: string; as_of?: string; age_days?: number; reason?: string };
type Company = {
  symbol: string; status: string; reason?: string;
  profile: { name: string; description: string; industry: string; industry_code: string; revenue_model: string; state_of_incorporation: string | null; fiscal_year_end: string | null; exchanges: string[] | null; source: string; observed_at: string | null };
  price: { value: number; date: string; source: string } | null;
  fundamentals: Record<string, Metric>; valuation: Record<string, Metric>; latest_filing: string | null;
  risks: { risk: string; detail: string; source: string }[];
  catalysts: { event: string; date: string; detail: string; source: string }[]; catalyst_note: string;
  signals: { system_view: string; signal: number | null; composite_score: number | null; proposal: { session_date: string; side: string; quantity: number; status: string } | null; why_not: string | null };
  news?: { cluster_id: string; headline: string; first_usable_at: string; category: { label: string } | null }[];
  tag: string; synthetic: boolean;
};

function fmt(m: Metric): string {
  if (m.value === null) return "NOT AVAILABLE";
  if (m.unit === "USD") return `${(m.value / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  return m.value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
function sourceLink(src?: string) {
  if (!src) return null;
  const url = src.split(" ").find((p) => p.startsWith("http"));
  const head = src.split(" ").slice(0, 2).join(" ");
  return url ? <a href={url} target="_blank" rel="noreferrer">{head}</a> : <span>{src}</span>;
}
function MetricTable({ rows }: { rows: Metric[] }) {
  return (
    <table><thead><tr><th>Measure</th><th className="num">Value</th><th>Unit</th><th>Period</th><th>Source</th><th className="num">Age (days)</th></tr></thead>
      <tbody>{rows.map((m) => m.status !== "OK"
        ? <tr key={m.label}><td>{m.label}</td><td colSpan={5} className="na">NOT AVAILABLE. {m.reason}</td></tr>
        : <tr key={m.label}><td>{m.label}</td><td className="num">{fmt(m)}</td><td className="muted">{m.unit === "USD" ? "USD millions" : m.unit}</td>
            <td className="muted">{m.period}</td><td className="small">{sourceLink(m.source)}</td><td className="num">{m.age_days}</td></tr>)}
      </tbody></table>
  );
}

export function CompanyScreen({ tick, initial }: { tick: number; initial?: string }) {
  const [sym, setSym] = useState(initial ?? "UPCO");
  const [input, setInput] = useState(initial ?? "UPCO");
  const [c, setC] = useState<Company | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  useEffect(() => { if (initial) { setSym(initial); setInput(initial); } }, [initial]);
  useEffect(() => {
    setC(null);
    getJSON<Company>(`/api/company/${encodeURIComponent(sym)}`).then(setC);
    getJSON<{ bars?: Bar[] }>(`/api/bars/${encodeURIComponent(sym)}?days=1300`).then((d) => setBars(d.bars ?? [])).catch(() => setBars([]));
  }, [sym, tick]);
  const submit = (e: FormEvent) => { e.preventDefault(); setSym(input.trim().toUpperCase()); };
  const f = c?.fundamentals ?? {};
  const order = ["revenue", "revenue_annual", "operating_income", "net_income", "net_income_annual", "eps_diluted", "eps_ttm", "assets", "equity"];
  return (
    <section className="page">
      <form className="page-head" onSubmit={submit}>
        <h1>{c?.status === "OK" ? `${c.profile.name} (${c.symbol})` : sym}</h1>
        <span><input aria-label="Company ticker" className="field" value={input} onChange={(e) => setInput(e.target.value)} /> <button type="submit">Open</button></span>
      </form>
      {!c ? <p className="muted">Loading</p> : c.status !== "OK" ? <p className="na">NOT AVAILABLE. {c.reason}</p> : (<>
        {c.synthetic && <div className="data-banner" role="note"><strong>DEMO DATA.</strong> Every price for this company is invented.</div>}
        <section className="panel conclusion-panel"><h2>Why the system would trade or abstain</h2>
          {c.signals.proposal ? <p><strong>{sideLabel(c.signals.proposal.side)} {c.signals.proposal.quantity} shares</strong> proposed for {c.signals.proposal.session_date}, status {c.signals.proposal.status}.</p>
            : <p><strong>No trade proposed.</strong> {c.signals.why_not ?? ""}</p>}
          <p>{c.signals.system_view}</p>
          <p className="muted small">{c.tag === "research_only" ? "Research only. Orders are blocked." : "Tradable in the simulator and the paper account."} Composite score {c.signals.composite_score === null ? "NOT AVAILABLE" : c.signals.composite_score.toFixed(2)}.</p>
        </section>
        <section className="panel"><h2>Price and volume{c.price ? `, close ${c.price.value.toFixed(2)} USD on ${c.price.date}, ${c.price.source}` : ""}</h2>
          {bars.length === 0 ? <p className="na">NOT AVAILABLE. No recorded prices for this company.</p> : <PriceChart bars={bars} height={360} label="Company price chart" />}
        </section>
        <div className="grid2 even">
          <section className="panel"><h2>Business</h2>
            <dl className="facts">
              <dt>What it does</dt><dd>{c.profile.description}</dd>
              <dt>Industry</dt><dd>{c.profile.industry}</dd>
              <dt>Revenue model</dt><dd className="na">{c.profile.revenue_model}</dd>
              <dt>Incorporated in</dt><dd>{c.profile.state_of_incorporation ?? "NOT AVAILABLE"}</dd>
              <dt>Fiscal year ends</dt><dd>{c.profile.fiscal_year_end ? `${c.profile.fiscal_year_end.slice(0, 2)}-${c.profile.fiscal_year_end.slice(2)}` : "NOT AVAILABLE"}</dd>
              <dt>Exchanges</dt><dd>{c.profile.exchanges?.join(", ") || "NOT AVAILABLE"}</dd>
            </dl>
            <p className="muted small">Source: {c.profile.source}{c.profile.observed_at ? `, recorded ${timeET(c.profile.observed_at)}` : ""}.</p>
          </section>
          <section className="panel"><h2>Material risks the system measures</h2>
            <ul className="plain list">{c.risks.map((r) => <li key={r.risk}><strong>{r.risk}.</strong> <span>{r.detail}.</span> <span className="muted small">{r.source}</span></li>)}</ul>
          </section>
        </div>
        <section className="panel"><h2>Financial performance from SEC filings{c.latest_filing ? `, latest filed ${timeET(c.latest_filing)}` : ""}</h2>
          <MetricTable rows={order.filter((k) => f[k]).map((k) => f[k])} />
        </section>
        <section className="panel"><h2>Valuation</h2><MetricTable rows={Object.values(c.valuation)} /></section>
        <div className="grid2 even">
          <section className="panel"><h2>Upcoming catalysts</h2>
            {c.catalysts.length === 0 ? <p className="muted">{c.catalyst_note}.</p> : (
              <ul className="plain list">{c.catalysts.map((k, i) => <li key={i}><strong>{k.date}</strong> <span>{k.event}, {k.detail}.</span> <span className="muted small">{k.source}</span></li>)}</ul>)}
          </section>
          <section className="panel"><h2>Recent news</h2>
            {(c.news ?? []).length === 0 ? <p className="muted">No stories naming it in the last 90 days.</p> : (
              <ul className="plain list">{c.news!.map((n) => <li key={n.cluster_id}><span className="muted small">{timeET(n.first_usable_at)}{n.category ? `, ${n.category.label}` : ""}</span><br /><span data-source-text>{n.headline}</span></li>)}</ul>)}
          </section>
        </div>
      </>)}
    </section>
  );
}
