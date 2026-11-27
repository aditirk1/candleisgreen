import { Fragment, useEffect, useState } from "react";
import { getJSON } from "../api";

type Facet = { capability: string; status: string; label: string; reason: string | null; usable: boolean };
type Asset = { id: string; label: string; research: Facet; history: Facet; paper_execution: Facet; extra: Facet[]; summary: string };

function Cell({ f }: { f: Facet }) {
  return <td title={f.reason ?? ""}><span className={f.usable ? (f.status === "available" ? "gain" : "") : "na"}>{f.usable ? (f.status === "available" ? "✓ Available" : "Limited") : "Not available"}</span></td>;
}

export function AssetClassesScreen({ tick }: { tick: number }) {
  const [rows, setRows] = useState<Asset[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { getJSON<{ asset_classes: Asset[] }>("/api/asset-classes").then((d) => setRows(d.asset_classes)); }, [tick]);
  if (!rows) return <div className="panel muted">Loading</div>;
  return (
    <section className="page">
      <div className="page-head"><h1>Asset classes</h1></div>
      <p className="muted">What each market supports today, from the capability registry. Click a row for the reasons. Only stocks and ETFs can be paper traded.</p>
      <div className="panel flush">
        <table><thead><tr><th>Asset class</th><th>Summary</th><th>Research</th><th>Historical prices</th><th>Paper trading</th></tr></thead>
          <tbody>{rows.map((a) => (<Fragment key={a.id}>
            <tr className="clickable" tabIndex={0} onClick={() => setOpen(open === a.id ? null : a.id)}
              onKeyDown={(e) => { if (e.key === "Enter") setOpen(open === a.id ? null : a.id); }} aria-expanded={open === a.id}>
              <td><strong>{a.label}</strong></td><td>{a.summary}</td><Cell f={a.research} /><Cell f={a.history} /><Cell f={a.paper_execution} /></tr>
            {open === a.id && (
              <tr className="detail"><td colSpan={5}>
                <dl className="facts">
                  {[["Research", a.research], ["Historical prices", a.history], ["Paper trading", a.paper_execution], ...a.extra.map((f) => [f.capability.replace(/_/g, " "), f] as [string, Facet])]
                    .map(([k, f]) => <Fragment key={k as string}><dt>{k as string}</dt><dd>{(f as Facet).label}</dd></Fragment>)}
                </dl>
              </td></tr>)}
          </Fragment>))}</tbody></table>
      </div>
    </section>
  );
}
