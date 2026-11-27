import { useEffect, useMemo, useState } from "react";
import { getJSON } from "../api";
import { pct, signed, timeET } from "../format";
import { Tech, Ticker } from "../stock";
import { load, save, useMode } from "../theme";

type Move = { ticker: string; session: string | null; move: number | null; reason?: string };
type Item = { feed: string; title: string; link: string; license: string; published_at: string | null; first_seen_at: string; first_usable_at: string };
type Cluster = {
  cluster_id: string; headline: string; summary: string | null; excerpt?: string; items: number; feeds: string[]; first_usable_at: string; published_at?: string | null;
  tickers: string[]; links: string[]; sectors?: Record<string, string>; model_relevance?: string[]; items_detail?: Item[];
  category: { id: string; label: string; what_it_is: string; can_affect: string; hypothesis?: string } | null;
  prices: { tickers: Move[]; market: { session: string; move: number; names: number } | null } | null;
  rank?: { score: number; materiality: string; components: { reason: string; points: number }[] };
};
const FEEDS: Record<string, string> = { fed_press: "Federal Reserve", sec_press: "SEC press release", sec_litigation: "SEC litigation release" };

function readSet(key: string): Set<string> { try { return new Set(JSON.parse(load(key) ?? "[]")); } catch { return new Set(); } }
function writeSet(key: string, s: Set<string>) { save(key, JSON.stringify(Array.from(s).slice(-500))); }

function StoryCard({ c, read, saved, onRead, onSave }: { c: Cluster; read: boolean; saved: boolean; onRead: () => void; onSave: () => void }) {
  const mode = useMode();
  const [open, setOpen] = useState(false);
  const mkt = c.prices?.market ? signed(c.prices.market.move, (x) => pct(x, 2)) : null;
  const sectors = Object.entries(c.sectors ?? {});
  return (
    <article className={`story${open ? " open" : ""}${read ? " read" : ""}`}>
      <div className="story-row">
        <button className="story-head" onClick={() => { setOpen(!open); if (!open) onRead(); }} aria-expanded={open}>
          <span className="story-meta">{timeET(c.first_usable_at)}</span>
          {c.category && <span className="tag">{c.category.label}</span>}
          <span className="story-title" data-source-text>{c.headline}</span>
          {c.tickers.length > 0 && <span className="story-tickers">{c.tickers.join(", ")}</span>}
        </button>
        <button className={saved ? "icon active" : "icon"} onClick={onSave} aria-pressed={saved} aria-label={saved ? `Unsave ${c.headline.slice(0, 40)}` : `Save ${c.headline.slice(0, 40)}`}>{saved ? "Saved" : "Save"}</button>
      </div>
      {open && (
        <div className="story-body">
          <div className="story-col">
            <h3>What happened</h3>
            {c.summary ? <p data-source-text>{c.summary}</p>
              : <p><span data-source-text>{c.headline}</span><br /><span className="muted small">The source excerpt only repeats the headline. Open the source for details.</span></p>}
            <p className="muted small">{c.feeds.map((f) => FEEDS[f] ?? f).join(", ")}{c.items > 1 ? `, ${c.items} reports of the same story` : ""}.
              {c.published_at ? ` Published ${timeET(c.published_at)}.` : " Publication time not given by the source."} Seen {timeET(c.items_detail?.[0]?.first_seen_at ?? c.first_usable_at)}.</p>
            <p className="small">{(c.items_detail ?? c.links.map((l) => ({ link: l, feed: c.feeds[0] } as Item))).map((it, i) => <a key={i} href={it.link} target="_blank" rel="noreferrer">{i === 0 ? "Read the source" : `Source ${i + 1}`}</a>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " ", el] : [el]), [])}</p>
          </div>
          <div className="story-col">
            <h3>Why it may matter</h3>
            {c.category ? <><p>{c.category.what_it_is}.</p><p>Can affect: {c.category.can_affect}.</p></> : <p className="muted">Not classified.</p>}
            {c.category?.hypothesis && <p className="hypothesis"><strong>Hypothesis, not tested:</strong> {c.category.hypothesis}.</p>}
            {(c.model_relevance ?? []).length > 0 && <p><strong>Your portfolio:</strong> {c.model_relevance!.join(". ")}.</p>}
            {sectors.length > 0 && <p className="muted small">Industries: {sectors.map(([t, s]) => `${t} ${s}`).join(", ")}.</p>}
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
            {mode === "advanced" && c.rank && <p className="muted small">Relevance {c.rank.score}: {c.rank.components.map((x) => `${x.reason} ${x.points > 0 ? "+" : ""}${x.points}`).join(", ") || "no component"}.</p>}
          </div>
        </div>)}
    </article>
  );
}

export function NewsScreen({ tick, ticker }: { tick: number; ticker?: string }) {
  const [view, setView] = useState<"live" | "recent">("recent");
  const [sort, setSort] = useState<"relevance" | "recency">("relevance");
  const [cat, setCat] = useState("all");
  const [sector, setSector] = useState("all");
  const [onlyWatch, setOnlyWatch] = useState(false);
  const [onlySaved, setOnlySaved] = useState(false);
  const [q, setQ] = useState("");
  const [showRoutine, setShowRoutine] = useState(false);
  const [read, setRead] = useState(() => readSet("news_read"));
  const [saved, setSaved] = useState(() => readSet("news_saved"));
  const [data, setData] = useState<{ view: string; clusters: Cluster[]; ranking?: { method: string } } | null>(null);
  useEffect(() => { getJSON<{ view: string; clusters: Cluster[] }>(`/api/news?view=${view}&sort=${sort}${ticker ? `&ticker=${ticker}` : ""}`).then(setData); }, [tick, view, sort, ticker]);
  const watch = useMemo(() => { try { return new Set<string>(JSON.parse(load("watchlist") ?? "[]")); } catch { return new Set<string>(); } }, [tick]);
  const all = data?.clusters ?? [];
  const cats = Array.from(new Set(all.map((c) => c.category?.label ?? "Other")));
  const sectors = Array.from(new Set(all.flatMap((c) => Object.values(c.sectors ?? {}))));
  const rows = all.filter((c) => (cat === "all" || (c.category?.label ?? "Other") === cat)
    && (sector === "all" || Object.values(c.sectors ?? {}).includes(sector))
    && (!onlyWatch || c.tickers.some((t) => watch.has(t)))
    && (!onlySaved || saved.has(c.cluster_id))
    && (!q || c.headline.toLowerCase().includes(q.toLowerCase())));
  const material = rows.filter((c) => (c.rank?.materiality ?? "ROUTINE") === "MATERIAL");
  const routine = rows.filter((c) => (c.rank?.materiality ?? "ROUTINE") !== "MATERIAL");
  const mark = (id: string) => { const s = new Set(read); s.add(id); setRead(s); writeSet("news_read", s); };
  const toggleSave = (id: string) => { const s = new Set(saved); if (s.has(id)) s.delete(id); else s.add(id); setSaved(s); writeSet("news_saved", s); };
  const card = (c: Cluster) => <StoryCard key={c.cluster_id} c={c} read={read.has(c.cluster_id)} saved={saved.has(c.cluster_id)} onRead={() => mark(c.cluster_id)} onSave={() => toggleSave(c.cluster_id)} />;
  return (
    <section className="page">
      <div className="page-head">
        <h1>Market intelligence{ticker ? `, ${ticker}` : ""}</h1>
        <div className="segmented small" role="group" aria-label="Time range">
          <button className={view === "live" ? "active" : ""} onClick={() => setView("live")}>72 hours</button>
          <button className={view === "recent" ? "active" : ""} onClick={() => setView("recent")}>90 days</button>
        </div>
      </div>
      <div className="toolbar">
        <input aria-label="Search headlines" className="field" placeholder="Search headlines" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="segmented small" role="group" aria-label="Sort">
          <button className={sort === "relevance" ? "active" : ""} onClick={() => setSort("relevance")}>Most relevant</button>
          <button className={sort === "recency" ? "active" : ""} onClick={() => setSort("recency")}>Newest</button>
        </div>
        <select aria-label="Category" className="field" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="all">All categories</option>{cats.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <select aria-label="Industry" className="field" value={sector} onChange={(e) => setSector(e.target.value)} disabled={sectors.length === 0}>
          <option value="all">{sectors.length ? "All industries" : "No industry data"}</option>{sectors.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <label className="small"><input type="checkbox" checked={onlyWatch} onChange={(e) => setOnlyWatch(e.target.checked)} /> Watchlist only</label>
        <label className="small"><input type="checkbox" checked={onlySaved} onChange={(e) => setOnlySaved(e.target.checked)} /> Saved only</label>
      </div>
      {!data ? <p className="muted">Loading</p> : rows.length === 0 ? <p className="muted">No stories match.</p> : (<>
        <h2 className="section">Material: names a listed company or moves rates ({material.length})</h2>
        {material.length === 0 ? <p className="muted">None in this view.</p> : <div className="stories">{material.map(card)}</div>}
        {routine.length > 0 && (
          <button className="link" onClick={() => setShowRoutine(!showRoutine)} aria-expanded={showRoutine}>
            {showRoutine ? "Hide" : "Show"} routine announcements ({routine.length})
          </button>)}
        {showRoutine && <div className="stories">{routine.map(card)}</div>}
        <p className="muted small">Official sources only. Most relevant puts stories that name a listed company, especially one you hold, and interest rate news first.</p>
        <Tech><p>Ranking: {data.ranking?.method}. Read and saved marks are kept in this browser.</p></Tech>
      </>)}
    </section>
  );
}
