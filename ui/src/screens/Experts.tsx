import { useEffect, useState } from "react";
import { getJSON } from "../api";

type Data = { sources: { license: string; description: string; research: string; paper_trading: string; note: string | null }[]; practitioner_note: string };

export function ExpertsScreen({ tick }: { tick: number }) {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => { getJSON<Data>("/api/experts").then(setData); }, [tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <>
      <section className="panel"><h2>Source registry</h2>
        <table><thead><tr><th>License</th><th>Source</th><th>Research use</th><th>Paper trading use</th><th>Note</th></tr></thead>
          <tbody>{data.sources.map((s) => (
            <tr key={s.license}><td>{s.license}</td><td>{s.description}</td><td>{s.research.toUpperCase()}</td><td>{s.paper_trading.toUpperCase()}</td><td className="muted">{s.note ?? ""}</td></tr>))}
          </tbody></table>
      </section>
      <section className="panel"><h2>Measured claim records</h2><p className="na">{data.practitioner_note}</p></section>
    </>
  );
}
