import { useEffect, useRef, useState } from "react";
import { getJSON } from "../api";
import { Bar, PriceChart } from "../chart";
import { pct, sideLabel, signed, timeET } from "../format";

type NewsRow = { cluster_id: string; headline: string; first_usable_at: string; category: { label: string } | null };
type Stock = {
  symbol: string; status: string; reason?: string; name: string; type: string; type_inferred: boolean;
  industry: { code: string; plain: string };
  price: { last: number | null; date: string | null; source: string | null; change: Record<string, number | null>; volatility_annual: number | null };
  system_view: string; signal: number | null; composite_score: number | null;
  proposal: { session_date: string; side: string; quantity: number; status: string } | null;
  can_trade: boolean; tag_note: string; news?: NewsRow[];
};
type Reason = {
  status: string; reason?: string;
  forecast: { model_id: string; model_version: string; signal_strength: number; as_of: string; calibration_status: string; data_snapshot_id: string; record_type: string; data_licenses: string[] } | null;
  risk: { verdict: string; reasons: string[]; checks_run: string[]; decided_at: string } | null;
  composite: { run_id: string | null; agreeing: [string, number][]; opposing: [string, number][]; exclusions: { signal_id: string; reasons: string[] }[]; uncertainty: { signal_id: string; mu_hat: number; prob_positive: number }[] };
  freshness: { last_close_date?: string; usable_from?: string; vendor?: string; status?: string };
  why_not: string | null;
};

export function StockPanel({ symbol, tick, onClose, onGo }: { symbol: string; tick: number; onClose: () => void; onGo: (screen: string, symbol: string) => void }) {
  const [s, setS] = useState<Stock | null>(null);
  const [r, setR] = useState<Reason | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const box = useRef<HTMLElement>(null);
  useEffect(() => {
    setS(null); setR(null); setBars([]);
    getJSON<Stock>(`/api/stock/${encodeURIComponent(symbol)}`).then(setS);
    getJSON<Reason>(`/api/reasoning?symbol=${encodeURIComponent(symbol)}`).then(setR).catch(() => setR(null));
    getJSON<{ status: string; bars?: Bar[] }>(`/api/bars/${encodeURIComponent(symbol)}`).then((d) => setBars(d.bars ?? [])).catch(() => setBars([]));
  }, [symbol, tick]);
  // Keyboard: focus moves into the drawer, Tab stays inside, Escape closes, focus returns to the opener.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>("button")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !box.current) return;
      const items = Array.from(box.current.querySelectorAll<HTMLElement>("button, a, input, select, [tabindex]:not([tabindex='-1'])"));
      if (items.length === 0) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    addEventListener("keydown", key);
    return () => { removeEventListener("keydown", key); opener?.focus?.(); };
  }, [onClose]);
  const fc = r?.status === "OK" ? r.forecast : null;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`About ${symbol}`} ref={box}>
        <div className="drawer-head">
          <div><div className="drawer-symbol">{symbol}</div><div className="muted">{s?.status === "OK" ? s.name : ""}</div></div>
          <button onClick={onClose} aria-label="Close">Close</button>
        </div>
        {!s ? <p className="muted">Loading</p> : s.status !== "OK" ? <p className="na">NOT AVAILABLE. {s.reason}</p> : (
          <>
            <section className="block conclusion">
              <h3>Conclusion</h3>
              {s.proposal
                ? <p><strong>{sideLabel(s.proposal.side)} {s.proposal.quantity} shares</strong> proposed for {s.proposal.session_date}, status {s.proposal.status}.</p>
                : <p><strong>No trade proposed.</strong> {r?.why_not ?? ""}</p>}
              <p>{s.system_view}</p>
              <p className="muted small">Horizon: about one month, decided again each trading day. Signal strength ranks names. It is not a forecast return or a probability, because the model is not calibrated.</p>
            </section>
            <div className="price-line">
              <span className="big">{s.price.last?.toFixed(2) ?? "NOT AVAILABLE"}</span>
              <span className="muted small">USD, close {s.price.date}, {s.price.source}</span>
            </div>
            <div className="changes">
              {Object.entries(s.price.change).map(([k, v]) => { const c = signed(v, (x) => pct(x, 1)); return <div key={k}><div className="muted small">{k} (%)</div><div className={c.cls}>{c.text}</div></div>; })}
            </div>
            {bars.length > 0 && <PriceChart bars={bars} height={220} label="Stock price chart" defaultRange="6M" />}
            <section className="block"><h3>Company</h3>
              <p>{s.name}. Industry: {s.industry.plain}.</p>
              <p className="muted small">{s.tag_note}.{s.type_inferred ? " Security type inferred from its name." : ""}</p>
            </section>
            <details className="block" open>
              <summary>Model reasoning</summary>
              {fc ? <p>{fc.model_id} {fc.model_version}, signal strength {fc.signal_strength.toFixed(2)}, {fc.record_type}, issued from data known at {timeET(fc.as_of)}. Calibration: {fc.calibration_status.replace(/_/g, " ").toLowerCase()}.</p>
                : <p className="muted">No forecast at the last decision.</p>}
            </details>
            <details className="block">
              <summary>Supporting and opposing signals</summary>
              {!r || r.status !== "OK" || !r.composite.run_id ? <p className="muted">NOT AVAILABLE. No Composite run covers this name.</p> : (<>
                <p>Supporting: {r.composite.agreeing.length ? r.composite.agreeing.map(([k, v]) => `${k} ${v.toFixed(3)}`).join(", ") : "none"}.</p>
                <p>Opposing: {r.composite.opposing.length ? r.composite.opposing.map(([k, v]) => `${k} ${v.toFixed(3)}`).join(", ") : "none"}.</p>
                {r.composite.exclusions.length > 0 && <p className="muted small">Excluded: {r.composite.exclusions.map((e) => e.signal_id).join(", ")}.</p>}
              </>)}
            </details>
            <details className="block">
              <summary>Risk checks and uncertainty</summary>
              {r?.risk ? <p>Last risk check {r.risk.verdict} at {timeET(r.risk.decided_at)}{r.risk.reasons.length ? `: ${r.risk.reasons.join(". ")}` : ""}.</p> : <p className="muted">No order has reached the risk service.</p>}
              <p className="muted small">How much it swings: {s.price.volatility_annual === null ? "NOT AVAILABLE" : `${pct(s.price.volatility_annual, 0)}% a year`}.
                {r?.composite.uncertainty?.length ? ` Chance each signal's edge is real: ${r.composite.uncertainty.map((u) => `${u.signal_id} ${(u.prob_positive * 100).toFixed(0)}%`).join(", ")}.` : ""}</p>
            </details>
            <details className="block">
              <summary>News and catalysts</summary>
              {(s.news ?? []).length === 0 ? <p className="muted">No stories naming it in the last 90 days. No catalyst calendar is available for free.</p> : (
                <ul className="plain">{s.news!.map((n) => <li key={n.cluster_id}><span className="muted small">{timeET(n.first_usable_at)}{n.category ? `, ${n.category.label}` : ""}</span><br /><span data-source-text>{n.headline}</span></li>)}</ul>)}
            </details>
            <details className="block">
              <summary>Data provenance</summary>
              <p className="muted small">Prices: {r?.freshness.vendor ?? s.price.source}, last close {r?.freshness.last_close_date ?? s.price.date}, usable from {timeET(r?.freshness.usable_from)}.
                {fc ? ` Forecast data snapshot ${fc.data_snapshot_id}, licenses ${fc.data_licenses.join(", ")}.` : ""} Composite score {s.composite_score === null ? "NOT AVAILABLE" : s.composite_score.toFixed(2)}.</p>
            </details>
            <div className="drawer-links">
              <button onClick={() => onGo("reasoning", s.symbol)}>Full reasoning</button>
              <button onClick={() => onGo("research", s.symbol)}>Research</button>
              <button onClick={() => onGo("markets", s.symbol)}>Company page</button>
            </div>
          </>)}
      </aside>
    </>
  );
}
