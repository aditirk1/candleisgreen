import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { pct, sideLabel, signed, usd } from "../format";
import { Term } from "../guide";
import { Ticker, useStock } from "../stock";
import { useMode } from "../theme";

type Metrics = { change_1m: number | null; change_1y: number | null; volatility_annual: number | null; median_dollar_volume_20d: number | null; price: number | null; as_of: string | null; source: string | null };
type Row = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; model: string; tier: number | null; status: string; direction?: string; horizon?: string; metrics?: Metrics };
type Data = { session_date: string | null; venue: string; rows: Row[]; note?: string };
type Sort = "signal" | "symbol" | "change_1y";

const millions = (v: number | null | undefined) => (v === null || v === undefined ? "NOT AVAILABLE" : (v / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 }));

export function OpportunitiesScreen({ tick }: { tick: number; onReason: (symbol: string) => void }) {
  const mode = useMode();
  const { open } = useStock();
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("signal");
  const [dir, setDir] = useState("all");
  useEffect(() => { getJSON<Data>("/api/opportunities").then(setData).catch((e) => setErr(String(e))); }, [tick]);
  if (err) return <div className="panel loss">{err}</div>;
  if (!data) return <div className="panel muted">Loading</div>;
  if (!data.session_date) return <div className="panel na">No proposals yet. The first decision runs after the market closes.</div>;
  const key = (r: Row) => sort === "symbol" ? r.symbol : sort === "change_1y" ? -(r.metrics?.change_1y ?? -1e9) : -Math.abs(r.signal_strength ?? 0);
  const rows = data.rows.filter((r) => dir === "all" || (dir === "long" ? ["buy", "buy_to_cover"].includes(r.side) : ["sell", "sell_short"].includes(r.side)))
    .sort((a, b) => { const x = key(a), y = key(b); return x < y ? -1 : x > y ? 1 : 0; });
  const th = (k: Sort, label: React.ReactNode, num = false) => (
    <th className={num ? "num" : ""} aria-sort={sort === k ? "descending" : "none"}><button className="th" onClick={() => setSort(k)}>{label}{sort === k ? " ▼" : ""}</button></th>);
  return (
    <section className="page">
      <div className="page-head"><h1>Opportunities for {data.session_date}</h1>
        <div className="segmented small" role="group" aria-label="Direction">
          {[["all", "All"], ["long", "Buys"], ["short", "Sells and shorts"]].map(([k, l]) => <button key={k} className={dir === k ? "active" : ""} onClick={() => setDir(k)}>{l}</button>)}
        </div>
      </div>
      <p className="muted">Click a row for the evidence. {data.note}.</p>
      <div className="panel flush">
        <table className="rows"><thead><tr>
          {th("symbol", "Ticker")}<th>Proposal</th>
          {th("signal", <Term k="signal_strength">Signal strength</Term>, true)}
          <th className="num">1 month (%)</th>{th("change_1y", "1 year (%)", true)}
          {mode === "advanced" && <><th className="num"><Term k="volatility">Volatility (% a year)</Term></th><th className="num"><Term k="adv20">Daily trading (USD millions)</Term></th><th><Term k="tier">Tier</Term></th></>}
          <th>Status</th></tr></thead>
          <tbody>{rows.map((r) => {
            const m1 = signed(r.metrics?.change_1m ?? null, (x) => pct(x, 1)), m12 = signed(r.metrics?.change_1y ?? null, (x) => pct(x, 1));
            return (
              <tr key={r.proposal_id} className="clickable" tabIndex={0} onClick={() => open(r.symbol)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(r.symbol); } }}
                aria-label={`${r.symbol}, ${sideLabel(r.side)} ${r.quantity}. Open evidence`}>
                <td><Ticker symbol={r.symbol} /></td><td>{sideLabel(r.side)} {r.quantity}</td>
                <td className="num">{r.signal_strength === null ? "NOT AVAILABLE" : r.signal_strength.toFixed(2)}</td>
                <td className={`num ${m1.cls}`}>{m1.text}</td><td className={`num ${m12.cls}`}>{m12.text}</td>
                {mode === "advanced" && <><td className="num">{r.metrics?.volatility_annual == null ? "NOT AVAILABLE" : pct(r.metrics.volatility_annual, 0)}</td>
                  <td className="num">{millions(r.metrics?.median_dollar_volume_20d)}</td><td>{r.tier ?? "NOT AVAILABLE"}</td></>}
                <td>{r.status}</td></tr>);
          })}</tbody></table>
      </div>
      {rows[0]?.metrics?.as_of && <p className="muted small">Prices to {rows[0].metrics.as_of}, {rows[0].metrics.source}. Last price {usd(rows[0].metrics.price)} for {rows[0].symbol}.</p>}
    </section>
  );
}
