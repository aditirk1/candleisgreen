import { useEffect, useRef, useState } from "react";
import { createChart, LineSeries, UTCTimestamp } from "lightweight-charts";
import { getJSON } from "../api";

type Inst = { instrument_id: string; symbol: string; name: string | null; type: string; type_inferred: boolean; tag: string; sector: string; status: string };
type Trial = { nct_id: string; title: string; overall_status: string; phases: string | null; primary_completion: string | null; primary_completion_type: string | null; enrollment: number | null; observed_at: string };
type Data = { trials?: Trial[]; instruments: Inst[]; selected: Inst | null; history: { date: string; close: number; vendor: string }[]; composite_score: number | null; status?: string; reason?: string };

function Chart({ points }: { points: Data["history"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    const css = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, { height: 260, layout: { background: { color: "transparent" }, textColor: css.getPropertyValue("--muted").trim() },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } }, timeScale: { borderVisible: false } });
    chart.addSeries(LineSeries, { color: css.getPropertyValue("--accent").trim(), lineWidth: 2 })
      .setData(points.map((p) => ({ time: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp, value: p.close })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  if (points.length === 0) return <p className="na">NOT AVAILABLE. No recorded closes.</p>;
  return <div ref={ref} aria-label="Price chart" />;
}

export function MarketsScreen({ tick, initial }: { tick: number; initial?: string }) {
  const [symbol, setSymbol] = useState(initial ?? "");
  const [q, setQ] = useState(initial ?? "");
  const [filter, setFilter] = useState("");
  const [data, setData] = useState<Data | null>(null);
  const [watch, setWatch] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem("watchlist") ?? "[]"); } catch { return []; } });
  function toggle(sym: string) {
    const next = watch.includes(sym) ? watch.filter((w) => w !== sym) : [...watch, sym];
    setWatch(next);
    try { localStorage.setItem("watchlist", JSON.stringify(next)); } catch { /* storage unavailable */ }
  }
  useEffect(() => { if (initial) { setSymbol(initial); setQ(initial); } }, [initial]);
  useEffect(() => { getJSON<Data>(`/api/markets${q ? `?symbol=${encodeURIComponent(q)}` : ""}`).then(setData); }, [tick, q]);
  if (!data) return <div className="panel muted">Loading</div>;
  if (data.status) return <div className="panel na">{data.status}. {data.reason}</div>;
  const list = data.instruments.filter((i) => !filter || i.symbol.includes(filter.toUpperCase()) || (i.name ?? "").toUpperCase().includes(filter.toUpperCase()));
  const s = data.selected;
  return (
    <div className="grid2">
      <section className="panel"><h2>Instruments</h2>
        <input aria-label="Search instruments" placeholder="Search ticker or name" value={filter} onChange={(e) => setFilter(e.target.value)} className="field" />
        <table><thead><tr><th>Ticker</th><th>Name</th><th>Tag</th><th>Sector (FF12)</th><th>Status</th></tr></thead>
          <tbody>{list.map((i) => (
            <tr key={i.instrument_id} onClick={() => { setSymbol(i.symbol); setQ(i.symbol); }} style={{ cursor: "pointer" }} className={s?.instrument_id === i.instrument_id ? "selected" : ""}>
              <td>{i.symbol}</td><td>{i.name ?? "NOT AVAILABLE"}</td><td>{i.tag.toUpperCase()}</td><td>{i.sector}</td><td>{i.status.toUpperCase()}</td></tr>))}
          </tbody></table>
      </section>
      <section className="panel"><h2>{s ? `${s.symbol} closes, as recorded` : "No instrument"}</h2>
        {s && <>
          <Chart points={data.history} />
          <dl className="facts">
            <dt>Type</dt><dd>{s.type}{s.type_inferred ? " (inferred)" : ""}</dd>
            <dt>Tag</dt><dd>{s.tag.toUpperCase()}{s.tag === "research_only" ? ". Orders blocked" : ""}</dd>
            <dt>Sector</dt><dd>{s.sector}</dd>
            <dt>Composite score</dt><dd>{data.composite_score === null ? "NOT AVAILABLE" : data.composite_score.toFixed(3)}</dd>
            <dt>Vendor</dt><dd>{data.history.at(-1)?.vendor ?? "NOT AVAILABLE"}</dd>
          </dl></>}
        {s && <button onClick={() => toggle(s.symbol)}>{watch.includes(s.symbol) ? `Remove ${s.symbol} from watchlist` : `Add ${s.symbol} to watchlist`}</button>}
        {(data.trials ?? []).length > 0 && (<>
          <h2 style={{ marginTop: 16 }}>Clinical trials, research only, as recorded</h2>
          <table><thead><tr><th>Trial</th><th>Phase</th><th>Status</th><th>Primary completion</th><th className="num">Enrollment</th></tr></thead>
            <tbody>{data.trials!.map((t) => (
              <tr key={t.nct_id} title={`${t.title}. Recorded ${t.observed_at}`}><td>{t.nct_id}</td><td>{t.phases ?? "NOT AVAILABLE"}</td><td>{t.overall_status}</td>
                <td>{t.primary_completion ?? "NOT AVAILABLE"} {t.primary_completion_type ? `(${t.primary_completion_type.toLowerCase()})` : ""}</td>
                <td className="num">{t.enrollment ?? "NOT AVAILABLE"}</td></tr>))}
            </tbody></table></>)}
        <h2 style={{ marginTop: 16 }}>Watchlist</h2>
        {watch.length === 0 ? <p className="muted">Empty. Kept in this browser only</p> : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{watch.map((w) => <button key={w} onClick={() => { setSymbol(w); setQ(w); }}>{w}</button>)}</div>)}
      </section>
    </div>
  );
}
