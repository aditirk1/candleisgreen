import { Fragment, ReactNode, useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { Bar, PriceChart } from "../chart";
import { pct, timeET } from "../format";
import { Tech } from "../stock";
import { load, save } from "../theme";

type Level = { key: string; label: string; state: string; note: string; checked: string | null };
type AssetLevels = { id: string; label: string; levels: Level[] };
type Check = { name: string; passed: boolean; reason: string };

const STATE: Record<string, { text: string; cls: string }> = {
  yes: { text: "✓ Yes", cls: "gain" }, partial: { text: "◐ Partly", cls: "" }, waiting: { text: "… Waiting", cls: "warn-text" }, no: { text: "✗ No", cls: "na" },
};
const SHORT: Record<string, string> = {
  source_exists: "Free source", adapter: "Connected", history_verified: "History checked", realtime_verified: "Current prices checked",
  research: "Research", simulation: "Simulation", broker_paper: "Broker paper trading", live_execution: "Live trading",
};
const usd = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "Not available" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));

function Checks({ checks }: { checks: Check[] }) {
  return <ul className="plain list">{checks.map((c, i) => <li key={i} className={c.passed ? "" : "loss"}>{c.passed ? "✓" : "✗"} {c.reason}</li>)}</ul>;
}

function Matrix({ rows }: { rows: AssetLevels[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const keys = rows[0]?.levels.map((l) => l.key) ?? [];
  return (
    <div className="panel flush scroll-x">
      <table><thead><tr><th>Asset class</th>{keys.map((k) => <th key={k}>{SHORT[k]}</th>)}</tr></thead>
        <tbody>{rows.map((a) => (<Fragment key={a.id}>
          <tr className="clickable" tabIndex={0} aria-expanded={open === a.id} onClick={() => setOpen(open === a.id ? null : a.id)}
            onKeyDown={(e) => { if (e.key === "Enter") setOpen(open === a.id ? null : a.id); }}>
            <td><strong>{a.label}</strong></td>
            {a.levels.map((l) => <td key={l.key} title={l.note}><span className={STATE[l.state].cls}>{STATE[l.state].text}</span></td>)}</tr>
          {open === a.id && (
            <tr className="detail"><td colSpan={keys.length + 1}>
              <dl className="facts">{a.levels.map((l) => <Fragment key={l.key}><dt>{l.label}</dt><dd>{STATE[l.state].text}. {l.note}{l.checked ? `. Checked ${l.checked}` : ""}.</dd></Fragment>)}</dl>
            </td></tr>)}
        </Fragment>))}</tbody></table>
    </div>
  );
}

/** Profit or loss at expiry against the underlying price. Plain SVG so it follows the theme tokens. */
function PayoffChart({ points, breakevens }: { points: { price: number; pnl: number }[]; breakevens: number[] }) {
  if (points.length < 2) return null;
  const W = 640, H = 220, P = 36;
  const xs = points.map((p) => p.price), ys = points.map((p) => p.pnl);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(0, ...ys), y1 = Math.max(0, ...ys);
  const sx = (x: number) => P + ((x - x0) / (x1 - x0 || 1)) * (W - 2 * P);
  const sy = (y: number) => H - P - ((y - y0) / (y1 - y0 || 1)) * (H - 2 * P);
  const d = points.map((p, i) => `${i ? "L" : "M"}${sx(p.price).toFixed(1)},${sy(p.pnl).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="payoff" role="img" aria-label="Profit or loss at expiry by underlying price">
      <line x1={P} x2={W - P} y1={sy(0)} y2={sy(0)} stroke="var(--chart-grid)" />
      <path d={d} fill="none" stroke="var(--chart-line)" strokeWidth={2} />
      {breakevens.map((b) => <line key={b} x1={sx(b)} x2={sx(b)} y1={P} y2={H - P} stroke="var(--muted)" strokeDasharray="4 4" />)}
      <text x={P} y={H - 8} fill="var(--chart-text)" fontSize="11">{x0.toFixed(0)}</text>
      <text x={W - P} y={H - 8} fill="var(--chart-text)" fontSize="11" textAnchor="end">{x1.toFixed(0)} underlying price at expiry</text>
      <text x={4} y={sy(y1) + 4} fill="var(--chart-text)" fontSize="11">{usd(y1)}</text>
      <text x={4} y={sy(y0) + 4} fill="var(--chart-text)" fontSize="11">{usd(y0)}</text>
    </svg>
  );
}

type LegRow = { kind: string; strike: string; quantity: string; premium: string };
function OptionsView({ tick }: { tick: number }) {
  const [under, setUnder] = useState("SPY");
  const [chain, setChain] = useState<{ status: string; reason?: string; rows?: any[]; note?: string } | null>(null);
  const [expiry, setExpiry] = useState("2026-12-18");
  const [legs, setLegs] = useState<LegRow[]>([{ kind: "call", strike: "600", quantity: "1", premium: "10" }, { kind: "call", strike: "610", quantity: "-1", premium: "6" }]);
  const [prof, setProf] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [model, setModel] = useState({ kind: "call", spot: "600", strike: "600", days: "30", volatility: "0.2", rate: "0.04" });
  const [mv, setMv] = useState<any>(null);
  useEffect(() => { getJSON<any>(`/api/assets/options/chain?underlying=${encodeURIComponent(under)}`).then(setChain).catch(() => setChain(null)); }, [tick]);
  const build = async () => {
    setErr(null);
    const body = { legs: legs.map((l) => ({ underlying: under, expiry, kind: l.kind, strike: Number(l.strike), quantity: Number(l.quantity), premium: Number(l.premium) })) };
    const r = await post("/api/assets/options/strategy", body);
    const j = await r.json();
    if (r.ok) setProf(j); else { setProf(null); setErr(typeof j.detail === "string" ? j.detail : "Check each leg's numbers"); }
  };
  const runModel = () => getJSON<any>(`/api/assets/options/model?${new URLSearchParams(model).toString()}`).then(setMv).catch(() => setMv(null));
  const set = (i: number, k: keyof LegRow, v: string) => setLegs(legs.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  return (<>
    <section className="panel"><h2>Options chain</h2>
      <div className="toolbar"><input className="field" aria-label="Underlying ticker" value={under} onChange={(e) => setUnder(e.target.value.toUpperCase())} />
        <button onClick={() => getJSON<any>(`/api/assets/options/chain?underlying=${encodeURIComponent(under)}`).then(setChain)}>Load chain</button></div>
      {!chain ? <p className="muted">Loading</p> : chain.status !== "OK" ? <p className="na">NOT AVAILABLE. {chain.reason}.</p> : (<>
        <p className="muted small">{chain.note}.</p>
        <div className="scroll"><table><thead><tr><th>Expiry</th><th>Type</th><th className="num">Strike</th><th className="num">Bid</th><th className="num">Ask</th><th className="num">Implied volatility</th><th className="num">Delta</th><th className="num">Open interest</th></tr></thead>
          <tbody>{chain.rows!.slice(0, 200).map((r) => <tr key={r.symbol}><td>{r.expiry}</td><td>{r.kind === "call" ? "Call" : "Put"}</td><td className="num">{r.strike}</td>
            <td className="num">{usd(r.bid, 2)}</td><td className="num">{usd(r.ask, 2)}</td><td className="num">{r.iv === null ? "Not available" : pct(r.iv, 1) + "%"}</td>
            <td className="num">{r.greeks ? r.greeks.delta.toFixed(2) : "Not available"}</td><td className="num">{r.open_interest ?? "Not available"}</td></tr>)}</tbody></table></div></>)}
    </section>
    <div className="grid2">
      <section className="panel"><h2>Strategy at expiry</h2>
        <p className="muted small">Enter the legs and the premium per share you would pay or receive. One contract covers 100 shares. This shows the result if every leg is held to expiry, not a forecast.</p>
        <div className="toolbar"><label className="small">Expiry <input className="field" type="date" aria-label="Expiry" value={expiry} onChange={(e) => setExpiry(e.target.value)} /></label></div>
        <table><thead><tr><th>Type</th><th>Strike</th><th>Contracts (negative to sell)</th><th>Premium per share</th><th></th></tr></thead>
          <tbody>{legs.map((l, i) => <tr key={i}>
            <td><select className="field" aria-label={`Leg ${i + 1} type`} value={l.kind} onChange={(e) => set(i, "kind", e.target.value)}><option value="call">Call</option><option value="put">Put</option></select></td>
            <td><input className="field" aria-label={`Leg ${i + 1} strike`} value={l.strike} onChange={(e) => set(i, "strike", e.target.value)} /></td>
            <td><input className="field" aria-label={`Leg ${i + 1} contracts`} value={l.quantity} onChange={(e) => set(i, "quantity", e.target.value)} /></td>
            <td><input className="field" aria-label={`Leg ${i + 1} premium`} value={l.premium} onChange={(e) => set(i, "premium", e.target.value)} /></td>
            <td><button className="link" onClick={() => setLegs(legs.filter((_, j) => j !== i))}>Remove</button></td></tr>)}</tbody></table>
        <div className="toolbar"><button onClick={() => setLegs([...legs, { kind: "put", strike: "590", quantity: "1", premium: "5" }])}>Add leg</button><button onClick={build}>Show payoff</button></div>
        {err && <p className="loss" role="status">{err}</p>}
        {prof && (<>
          <dl className="facts">
            <dt>Paid or received to open</dt><dd>{prof.net_premium >= 0 ? `Pay ${usd(prof.net_premium)} USD` : `Receive ${usd(-prof.net_premium)} USD`}</dd>
            <dt>Largest possible loss</dt><dd className={prof.max_loss === null ? "loss" : ""}>{prof.max_loss === null ? "No limit. The risk checks refuse this" : `${usd(prof.max_loss)} USD`}</dd>
            <dt>Largest possible gain</dt><dd>{prof.max_gain === null ? "No limit" : `${usd(prof.max_gain)} USD`}</dd>
            <dt>Break-even at expiry</dt><dd>{prof.breakevens.length ? prof.breakevens.map((b: number) => b.toFixed(2)).join(", ") : "None"}</dd>
          </dl>
          <PayoffChart points={prof.points} breakevens={prof.breakevens} /></>)}
      </section>
      <section className="panel"><h2>Theoretical value</h2>
        <p className="muted small">The Black-Scholes model with inputs you choose. A model value, never a market price.</p>
        <dl className="facts">{(["kind", "spot", "strike", "days", "volatility", "rate"] as const).map((k) => <Fragment key={k}>
          <dt>{{ kind: "Type", spot: "Underlying price", strike: "Strike", days: "Days to expiry", volatility: "Volatility (0.2 is 20%)", rate: "Interest rate (0.04 is 4%)" }[k]}</dt>
          <dd>{k === "kind" ? <select className="field" aria-label="Model type" value={model.kind} onChange={(e) => setModel({ ...model, kind: e.target.value })}><option value="call">Call</option><option value="put">Put</option></select>
            : <input className="field" aria-label={`Model ${k}`} value={model[k]} onChange={(e) => setModel({ ...model, [k]: e.target.value })} />}</dd></Fragment>)}</dl>
        <button onClick={runModel}>Calculate</button>
        {mv && <dl className="facts"><dt>Model value per share</dt><dd>{mv.price.toFixed(2)}</dd><dt>Delta</dt><dd>{mv.delta.toFixed(3)}</dd><dt>Gamma</dt><dd>{mv.gamma.toFixed(4)}</dd>
          <dt>Theta, per day</dt><dd>{mv.theta_per_day.toFixed(3)}</dd><dt>Vega, per volatility point</dt><dd>{mv.vega_per_vol_point.toFixed(3)}</dd></dl>}
      </section>
    </div>
  </>);
}

function CryptoView({ tick }: { tick: number }) {
  const [sym, setSym] = useState("BTC/USD");
  const [d, setD] = useState<any>(null);
  const [book, setBook] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [order, setOrder] = useState({ side: "buy", notional: "1000" });
  const [res, setRes] = useState<any>(null);
  const loadAll = () => getJSON<any>(`/api/assets/crypto?symbol=${encodeURIComponent(sym)}`).then(setD).catch(() => setD(null));
  useEffect(() => { loadAll(); }, [tick, sym]);
  const refresh = async () => { setMsg("Recording from Alpaca"); const r = await post("/api/assets/crypto/refresh"); const j = await r.json(); setMsg(r.ok ? "Up to date" : j.detail); loadAll(); };
  const getBook = () => getJSON<any>(`/api/assets/crypto/book?symbol=${encodeURIComponent(sym)}`).then(setBook);
  const simulate = async () => {
    // One ID per press. A retried request with the same ID returns the first result instead of filling twice.
    const id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    const r = await post("/api/assets/crypto/simulate", { client_order_id: id, side: order.side, symbol: sym, notional: Number(order.notional) });
    const j = await r.json(); setRes(r.ok ? j : { status: "error", detail: j.detail }); loadAll();
  };
  if (!d) return <p className="muted">Loading</p>;
  return (<>
    <section className="panel"><h2>Crypto pairs</h2>
      <p className="muted small">{d.source}. Daily bars run from midnight to midnight UTC, every day of the week.</p>
      {!d.recorded && <p className="na">Not recorded yet. Press Record to fetch daily history from Alpaca. No key is needed.</p>}
      <div className="toolbar"><button onClick={refresh}>Record latest</button>{msg && <span role="status" className="small">{msg}</span>}</div>
      <table><thead><tr><th>Pair</th><th className="num">Days</th><th>Last day</th><th className="num">Close (USD)</th><th className="num">30 days (%)</th><th className="num">Volatility, yearly (%)</th><th className="num">Worst fall from a peak (%)</th></tr></thead>
        <tbody>{d.rows.map((r: any) => <tr key={r.symbol} className={r.symbol === sym ? "selected clickable" : "clickable"} onClick={() => setSym(r.symbol)}>
          <td><strong>{r.symbol}</strong></td><td className="num">{r.days}</td><td>{r.last_date ?? "Not recorded"}</td><td className="num">{usd(r.close, 2)}</td>
          <td className={`num ${r.change_30d > 0 ? "gain" : r.change_30d < 0 ? "loss" : ""}`}>{r.change_30d === null ? "Not available" : `${r.change_30d > 0 ? "▲ +" : r.change_30d < 0 ? "▼ " : ""}${pct(r.change_30d, 1)}`}</td>
          <td className="num">{r.volatility === null ? "Not available" : pct(r.volatility, 0)}</td><td className="num">{r.max_drawdown === null ? "Not available" : pct(r.max_drawdown, 0)}</td></tr>)}</tbody></table>
    </section>
    {d.bars.length > 0 && <section className="panel"><h2>{sym} daily prices</h2><PriceChart bars={d.bars as Bar[]} label="Crypto price chart" height={320} /></section>}
    <div className="grid2 even">
      <section className="panel"><h2>Order book now</h2>
        <button onClick={getBook}>Read the {sym} book</button>
        {book && (book.status !== "OK" ? <p className="na">NOT AVAILABLE. {book.reason}.</p> : <dl className="facts">
          <dt>Midpoint</dt><dd>{usd(book.mid, 2)} USD</dd><dt>Spread</dt><dd>{book.spread_bps.toFixed(1)} basis points</dd>
          <dt>Buyers within {book.band_bps} bps</dt><dd>{usd(book.bid_depth_usd)} USD</dd><dt>Sellers within {book.band_bps} bps</dt><dd>{usd(book.ask_depth_usd)} USD</dd>
          <dt>Fee for an order that takes liquidity</dt><dd>{book.taker_fee_bps} basis points</dd><dt>Book time</dt><dd>{book.time ? timeET(book.time) : "Not given"}</dd>
          <dt>Fresh enough to use</dt><dd className={book.fresh ? "" : "loss"}>{book.fresh ? "✓ Yes" : "✗ No"}. {book.freshness}</dd></dl>)}
      </section>
      <section className="panel"><h2>Practice order, simulated</h2>
        <p className="muted small">Fills against the live Alpaca book with Alpaca's fees. No broker order is sent. Crypto cannot be sold short or bought on margin. An order book older than 15 seconds is refused. The practice balance is saved and survives restarts.</p>
        <div className="toolbar">
          <div className="segmented small" role="group" aria-label="Side">{["buy", "sell"].map((s) => <button key={s} className={order.side === s ? "active" : ""} onClick={() => setOrder({ ...order, side: s })}>{s === "buy" ? "Buy" : "Sell"}</button>)}</div>
          <label className="small">Amount (USD) <input className="field" aria-label="Order amount in USD" value={order.notional} onChange={(e) => setOrder({ ...order, notional: e.target.value })} /></label>
          <button onClick={simulate}>Simulate</button></div>
        {res && (res.status === "error" ? <p className="loss">{res.detail}</p> : <>
          <p><strong>{res.status === "filled" ? "Filled in the simulator" : "Blocked by the risk checks"}</strong>{res.fill ? `: ${res.fill.quantity.toFixed(6)} at ${usd(res.fill.price, 2)} USD, fee ${usd(res.fill.fee_usd, 2)} USD` : ""}.</p>
          <Checks checks={res.checks} /></>)}
        <p className="small">Practice cash {usd(d.simulator.cash, 2)} USD{Object.keys(d.simulator.holdings).length ? `. Holding ${Object.entries(d.simulator.holdings).map(([k, v]) => `${(v as number).toFixed(6)} ${k.split("/")[0]}`).join(", ")}` : ""}.</p>
      </section>
    </div>
  </>);
}

function ForexView({ tick }: { tick: number }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { getJSON<any>("/api/assets/forex").then(setD).catch(() => setD(null)); }, [tick]);
  if (!d) return <p className="muted">Loading</p>;
  return (
    <section className="panel"><h2>Forex through an OANDA practice account</h2>
      {d.status !== "OK" ? (<>
        <p className="na">NOT AVAILABLE yet. Two steps turn it on:</p>
        <ol>{d.steps.map((s: string, i: number) => <li key={i}>{s}.</li>)}</ol>
        <Tech><p>License setting: {d.license_file}.</p></Tech></>)
        : <p>Connected. {Object.keys(d.stored).length} pairs recorded.</p>}
      <dl className="facts"><dt>Pairs</dt><dd>{d.instruments.map((i: string) => i.replace("_", "/")).join(", ")}</dd>
        <dt>Widest spread allowed</dt><dd>{d.limits.max_spread_pips} pips</dd>
        <dt>Largest position</dt><dd>{pct(d.limits.max_notional_pct_equity, 0)}% of the account</dd>
        <dt>All positions together</dt><dd>At most {d.limits.max_gross_leverage} times the account. Nothing is borrowed to trade</dd></dl>
      <p className="muted small">OANDA's prices and spreads are OANDA's own, not the whole currency market. {d.reference}.</p>
    </section>
  );
}

function FuturesView({ tick }: { tick: number }) {
  const [d, setD] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [csv, setCsv] = useState(() => load("futures_csv") ?? "");
  const [cont, setCont] = useState<any>(null);
  const [prod, setProd] = useState("ES");
  const reload = () => getJSON<any>("/api/assets/futures").then(setD).catch(() => setD(null));
  useEffect(() => { reload(); }, [tick]);
  const refresh = async () => { setMsg("Reading CFTC reports"); const r = await post("/api/assets/futures/cot/refresh"); const j = await r.json(); setMsg(r.ok ? "Up to date" : j.detail); reload(); };
  const upload = async () => { save("futures_csv", csv); const r = await post("/api/assets/futures/settlements", { text: csv }); const j = await r.json(); setMsg(r.ok ? `Stored ${j.stored} settlement prices for ${j.contracts.join(", ")}` : j.detail); reload(); };
  const showCont = () => getJSON<any>(`/api/assets/futures/continuous?product=${prod}`).then(setCont);
  if (!d) return <p className="muted">Loading</p>;
  return (<>
    <section className="panel"><h2>Contracts</h2>
      <p className="muted small">{d.prices}. Contract terms come from CME's published specifications and are not yet checked against CME, because its site did not answer.</p>
      <div className="scroll-x"><table><thead><tr><th>Contract</th><th className="num">Size</th><th className="num">Tick value (USD)</th><th>Settles in</th><th>Hold now</th><th>Roll on</th><th>Last trading day</th><th>Terms</th></tr></thead>
        <tbody>{d.products.map((p: any) => <tr key={p.code}><td><strong>{p.code}</strong> {p.name}</td><td className="num">{p.multiplier} per point</td><td className="num">{p.tick_value_usd}</td>
          <td>{p.settlement === "cash" ? "Cash" : "Delivery"}</td><td>{p.front ?? "Not available"}</td><td>{p.roll_date ?? (p.calendar_reason ? "Holiday list missing" : "")}</td><td>{p.last_trade ?? ""}</td>
          <td className={p.verified ? "gain" : "warn-text"}>{p.verified ? "✓ Checked" : "Not yet checked"}</td></tr>)}</tbody></table></div>
    </section>
    <section className="panel"><h2>Who holds futures, CFTC weekly report</h2>
      <div className="toolbar"><button onClick={refresh}>Read latest reports</button>{msg && <span role="status" className="small">{msg}</span>}</div>
      {d.products.every((p: any) => !p.cot) ? <p className="na">Not recorded yet. Press Read latest reports. The CFTC publishes them free every Friday.</p> : (
        <div className="grid2 even">{d.products.filter((p: any) => p.cot).map((p: any) => (
          <div key={p.code}>
            <h3>{p.name}, positions on {p.cot.report_date}</h3>
            <table><thead><tr><th>Group</th><th className="num">Net contracts</th><th className="num">Share of all open contracts (%)</th><th className="num">Change in a week</th></tr></thead>
              <tbody>{p.cot.groups.map((g: any) => <tr key={g.label}><td>{g.label}</td><td className="num">{g.net > 0 ? "+" : ""}{g.net.toLocaleString("en-US")}</td>
                <td className="num">{pct(g.net_pct_oi, 1)}</td><td className="num">{g.week_change === null ? "Not available" : `${g.week_change > 0 ? "+" : ""}${g.week_change.toLocaleString("en-US")}`}</td></tr>)}</tbody></table>
            <p className="muted small">{p.cot.lead_percentile === null ? `Fewer than 26 reports stored, so no comparison with the past.` : `${p.cot.lead_group}: net position higher than in ${pct(p.cot.lead_percentile, 0)}% of the last ${p.cot.window_reports} weeks.`} A description of positions, not a signal. Counts from {timeET(p.cot.usable_from)}.</p>
          </div>))}</div>)}
      <p className="muted small">{d.cot_source}.</p>
    </section>
    <section className="panel"><h2>Your settlement prices</h2>
      <p className="muted small">Paste settlement prices you downloaded yourself, one per line as date, contract, settle (for example 2026-12-11,ESZ26,6030). Stored as research only.</p>
      <textarea className="field" aria-label="Settlement prices" rows={5} style={{ width: "100%" }} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={"date,contract,settle\n2026-12-11,ESZ26,6030"} />
      <div className="toolbar"><button onClick={upload} disabled={!csv.trim()}>Store prices</button>
        <select className="field" aria-label="Product" value={prod} onChange={(e) => setProd(e.target.value)}>{d.products.map((p: any) => <option key={p.code} value={p.code}>{p.code}</option>)}</select>
        <button onClick={showCont}>Join into one series</button></div>
      {cont && (cont.status !== "OK" ? <p className="na">NOT AVAILABLE. {cont.reason}.</p> : <>
        <p className="muted small">{cont.points.length} days, adjusted at each roll so returns carry across contracts. {cont.label}.</p>
        <PriceChart bars={cont.points.map((p: any) => ({ date: p.date, close: p.adjusted }))} candles={false} label="Continuous futures chart" height={260} /></>)}
    </section>
  </>);
}

const VIEWS: [string, string, (p: { tick: number }) => ReactNode][] = [
  ["options", "Options", (p) => <OptionsView {...p} />], ["crypto", "Crypto", (p) => <CryptoView {...p} />],
  ["forex", "Forex", (p) => <ForexView {...p} />], ["futures", "Futures", (p) => <FuturesView {...p} />],
];

export function AssetClassesScreen({ tick }: { tick: number }) {
  const [rows, setRows] = useState<AssetLevels[] | null>(null);
  const [view, setView] = useState(() => load("asset_view") ?? "crypto");
  useEffect(() => { getJSON<{ asset_classes: AssetLevels[] }>("/api/assets/levels").then((d) => setRows(d.asset_classes)); }, [tick]);
  const pick = (v: string) => { setView(v); save("asset_view", v); };
  return (
    <section className="page">
      <div className="page-head"><h1>Asset classes</h1></div>
      <p className="muted">What each market supports today, from a free source existing to live trading. Click a row for the details. Only US stocks and ETFs can be paper traded through a broker. Live trading is never built.</p>
      {!rows ? <p className="muted">Loading</p> : <Matrix rows={rows} />}
      <div className="page-head" style={{ marginTop: 16 }}>
        <div className="segmented" role="group" aria-label="Asset class view">{VIEWS.map(([k, label]) => <button key={k} className={view === k ? "active" : ""} onClick={() => pick(k)}>{label}</button>)}</div>
      </div>
      {VIEWS.find(([k]) => k === view)?.[2]({ tick })}
      <Tech><p>Levels from config/capabilities.yaml (asset_* entries). Settings in config/default.yaml under assets. Futures terms in config/futures_contracts.yaml.</p></Tech>
    </section>
  );
}
