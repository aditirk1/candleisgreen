import { useEffect, useState } from "react";
import { getJSON, post } from "../api";
import { timeET } from "../format";

type Card = { claim_type: string; title: string; direction: string; horizon: string | null; instruments: string[] };
type Capture = { capture_id: string; kind: string; capture_hash: string; received_at: string; url: string | null; filename: string | null; summary: string | null; status: string; request: string | null; cards: Card[]; sent_to_factory: boolean };

export function InboxPanel({ tick }: { tick: number }) {
  const [items, setItems] = useState<Capture[]>([]);
  const [kind, setKind] = useState<"text" | "link">("text");
  const [content, setContent] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => { getJSON<{ captures: Capture[] }>("/api/inbox").then((d) => setItems(d.captures)); }, [tick, n]);

  async function send(body: Record<string, string>) {
    const r = await post("/api/inbox", body);
    const out = await r.json().catch(() => ({}));
    setMsg(r.ok ? (out.duplicate ? "Already captured" : `Captured. ${out.cards.length} claims found. ${out.request ?? ""}`) : `Not captured. ${out.detail ?? r.status}`);
    if (r.ok) setContent("");
    setN((x) => x + 1);
  }
  async function sendFile(f: File) {
    const buf = new Uint8Array(await f.arrayBuffer());
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    send({ kind: "file", filename: f.name, content: btoa(bin) });
  }
  return (
    <section className="panel"><h2>Research Capture Inbox</h2>
      <p className="muted">Paste a link or text, or add a file. Only a hash, the time, a short summary and extracted claims are kept. Links are not fetched automatically.</p>
      <form onSubmit={(e) => { e.preventDefault(); send(kind === "link" ? { kind, url: content } : { kind, content }); }} style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className={kind === "text" ? "active" : ""} onClick={() => setKind("text")}>Text</button>
          <button type="button" className={kind === "link" ? "active" : ""} onClick={() => setKind("link")}>Link</button>
          <label className="muted">File <input type="file" aria-label="Capture file" onChange={(e) => e.target.files?.[0] && sendFile(e.target.files[0])} /></label>
        </div>
        {kind === "text"
          ? <textarea aria-label="Capture text" className="field" rows={4} value={content} onChange={(e) => setContent(e.target.value)} />
          : <input aria-label="Capture link" className="field" value={content} onChange={(e) => setContent(e.target.value)} placeholder="https://" />}
        <div><button type="submit" disabled={!content.trim()}>Capture</button></div>
      </form>
      {msg && <p role="status">{msg}</p>}
      {items.length > 0 && (
        <table><thead><tr><th>Received</th><th>Kind</th><th>Status</th><th>Summary or request</th><th className="num">Claims</th><th>Hash</th></tr></thead>
          <tbody>{items.map((c) => (
            <tr key={c.capture_id} title={c.cards.map((k) => `${k.claim_type}: ${k.title}`).join("\n")}>
              <td>{timeET(c.received_at)}</td><td>{c.kind}</td><td className={c.status === "EXTRACTED" ? "" : "na"}>{c.status}</td>
              <td>{c.request ?? c.summary ?? c.url ?? ""}</td><td className="num">{c.cards.length}</td><td className="muted">{c.capture_hash.slice(0, 12)}</td></tr>))}
          </tbody></table>)}
    </section>
  );
}
