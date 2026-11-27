import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { pct, signed, timeET } from "../format";
import { Ticker } from "../stock";

type Move = { ticker: string; session: string | null; move: number | null; reason?: string };
type Cluster = {
  cluster_id: string; headline: string; summary: string | null; items: number; feeds: string[]; first_usable_at: string; tickers: string[]; links: string[];
  category: { id: string; label: string; what_it_is: string; can_affect: string } | null;
  prices: { tickers: Move[]; market: { session: string; move: number; names: number } | null } | null;
};
const FEEDS: Record<string, string> = { fed_press: "Federal Reserve", sec_press: "SEC press release", sec_litigation: "SEC litigation" };

function StoryCard({ c }: { c: Cluster }) {
  const [open, setOpen] = useState(false);
  const mkt = c.prices?.market ? signed(c.prices.market.move, (x) => pct(x, 2)) : null;
  return (
    <article className={open ? "story open" : "story"}>
      <button className="story-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="story-meta">{timeET(c.first_usable_at)}</span>
        {c.category && <span className="tag">{c.category.label}</span>}
        <span className="story-title" data-source-text>{c.headline}</span>
        {c.tickers.length > 0 && <span className="story-tickers">{c.tickers.join(", ")}</span>}
      </button>
      {open && (
        <div className="story-body">
          <div className="story-col">
            <h3>What happened</h3>
            <p data-source-text>{c.summary ?? c.headline}</p>
            <p className="muted small">{c.feeds.map((f) => FEEDS[f] ?? f).join(", ")}{c.items > 1 ? `, ${c.items} reports of the same story` : ""}. <a href={c.links[0]} target="_blank" rel="noreferrer">Read the source</a></p>
          </div>
          <div className="story-col">
            <h3>Why it may matter</h3>
            {c.category ? <><p>{c.category.what_it_is}.</p><p>Can affect: {c.category.can_affect}.</p></> : <p className="muted">Not classified.</p>}
            <p className="muted small">A general description, not a forecast.</p>
          </div>
          <div className="story-col">
            <h3>What prices did</h3>
            {c.tickers.length === 0 ? <p className="muted">No listed company is named.</p> : (
              <ul className="plain">{(c.prices?.tickers ?? c.tickers.map((t) => ({ ticker: t, move: null, session: null, reason: "price data busy" }))).map((m) => {
                const v = signed(m.move, (x) => pct(x, 2));
                return <li key={m.ticker}><Ticker symbol={m.ticker} /> {m.move === null ? <span className="muted">NOT AVAILABLE, {m.reason}</span> : <><span className={v.cls}>{v.text}%</span> <span className="muted small">next session {m.session}</span></>}</li>;
              })}</ul>)}
            {mkt && <p className="small">All recorded stocks, same session: <span className={mkt.cls}>{mkt.text}%</span></p>}
            <p className="muted small">An observation, not proof the story caused it.</p>
          </div>
        </div>)}
    </article>
  );
}

export function NewsScreen({ tick, ticker }: { tick: number; ticker?: string }) {
  const [view, setView] = useState<"live" | "recent">("live");
  const [cat, setCat] = useState("all");
  const [data, setData] = useState<{ view: string; clusters: Cluster[] } | null>(null);
  useEffect(() => { getJSON<{ view: string; clusters: Cluster[] }>(`/api/news?view=${view}${ticker ? `&ticker=${ticker}` : ""}`).then(setData); }, [tick, view, ticker]);
  const cats = Array.from(new Set((data?.clusters ?? []).map((c) => c.category?.label ?? "Other")));
  const [showRest, setShowRest] = useState(false);
  const rows = (data?.clusters ?? []).filter((c) => cat === "all" || (c.category?.label ?? "Other") === cat);
  // Shown first: a story that names a listed company, or interest rate news that moves the whole market.
  const relevant = (c: Cluster) => c.tickers.length > 0 || c.category?.id === "monetary_policy";
  const main = rows.filter(relevant);
  const rest = rows.filter((c) => !relevant(c));
  return (
    <section className="page">
      <div className="page-head">
        <h1>News{ticker ? `, ${ticker} only` : ""}</h1>
        <div className="segmented" role="group" aria-label="Time range">
          <button className={view === "live" ? "active" : ""} onClick={() => setView("live")}>Last 72 hours</button>
          <button className={view === "recent" ? "active" : ""} onClick={() => setView("recent")}>Last 90 days</button>
        </div>
      </div>
      <p className="muted">Official sources only. Click a story for the summary, why it may matter and what prices did. Stories that name no listed company are under Other official news.</p>
      {cats.length > 1 && (
        <div className="filters" role="group" aria-label="Category">
          <button className={cat === "all" ? "active" : ""} onClick={() => setCat("all")}>All ({data!.clusters.length})</button>
          {cats.map((k) => <button key={k} className={cat === k ? "active" : ""} onClick={() => setCat(k)}>{k} ({data!.clusters.filter((c) => (c.category?.label ?? "Other") === k).length})</button>)}
        </div>)}
      {!data ? <p className="muted">Loading</p> : rows.length === 0 ? <p className="muted">No stories in this view</p> : (<>
        <h2 className="section">Names a listed company or concerns interest rates ({main.length})</h2>
        {main.length === 0 ? <p className="muted">None in this view</p> : <div className="stories">{main.map((c) => <StoryCard key={c.cluster_id} c={c} />)}</div>}
        {rest.length > 0 && (
          <button className="link" onClick={() => setShowRest(!showRest)} aria-expanded={showRest}>
            {showRest ? "Hide" : "Show"} other official news ({rest.length})
          </button>)}
        {showRest && <div className="stories">{rest.map((c) => <StoryCard key={c.cluster_id} c={c} />)}</div>}
      </>)}
    </section>
  );
}
