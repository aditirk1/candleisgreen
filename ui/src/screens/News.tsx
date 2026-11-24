import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { timeET } from "../format";

type Cluster = { cluster_id: string; headline: string; items: number; feeds: string[]; first_usable_at: string; tickers: string[]; links: string[] };

function shown(cs: Cluster[], ticker?: string): Cluster[] {
  return ticker ? cs.filter((c) => c.tickers.includes(ticker)) : cs;
}

export function NewsScreen({ tick, ticker }: { tick: number; ticker?: string }) {
  const [view, setView] = useState<"live" | "recent">("recent");
  const [data, setData] = useState<{ view: string; clusters: Cluster[] } | null>(null);
  useEffect(() => { getJSON<{ view: string; clusters: Cluster[] }>(`/api/news?view=${view}`).then(setData); }, [tick, view]);
  return (
    <section className="panel"><h2>News, {data?.view ?? view.toUpperCase()}, clustered by story{ticker ? `, ${ticker} only` : ""}</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button className={view === "live" ? "active" : ""} onClick={() => setView("live")}>NEWS LIVE (72 hours)</button>
        <button className={view === "recent" ? "active" : ""} onClick={() => setView("recent")}>RECENT (90 days)</button>
      </div>
      <p className="muted">What happened, from official feeds only. What it may mean and what prices did are kept on the Reasoning screen.</p>
      {!data ? <p className="muted">Loading</p> : shown(data.clusters, ticker).length === 0 ? <p className="muted">No stories in this view</p> : (
        <table><thead><tr><th>First seen</th><th>Story</th><th className="num">Items</th><th>Sources</th><th>Tickers</th></tr></thead>
          <tbody>{shown(data.clusters, ticker).map((c) => (
            <tr key={c.cluster_id}><td>{timeET(c.first_usable_at)}</td>
              <td><a href={c.links[0]} target="_blank" rel="noreferrer" style={{ color: "var(--text)" }}>{c.headline}</a></td>
              <td className="num">{c.items}</td><td className="muted">{c.feeds.join(", ")}</td><td>{c.tickers.join(", ") || "None linked"}</td></tr>))}
          </tbody></table>)}
    </section>
  );
}
