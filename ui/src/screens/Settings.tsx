import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { feedName } from "../labels";
import { useMode } from "../theme";
import { MODE_LABELS } from "../format";

type Data = { mode: string; venue: string; live_trading: string; credentials: { name: string; purpose: string; status: string }[]; monthly_cost_usd: number; config_version: string; providers: string[] };

export function SettingsScreen({ tick, theme, setTheme, guide, setGuide }: { tick: number; theme: string; setTheme: (t: "light" | "dark") => void; guide: boolean; setGuide: (g: boolean) => void }) {
  const mode = useMode();
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => { getJSON<Data>("/api/settings").then(setData); }, [tick]);
  if (!data) return <div className="panel muted">Loading</div>;
  return (
    <div className="grid2">
      <section className="panel"><h2>API keys and data sources</h2>
        <table><thead><tr><th>Variable</th><th>Purpose</th><th>Status</th></tr></thead>
          <tbody>{data.credentials.map((c) => (
            <tr key={c.name}><td>{c.name}</td><td>{c.purpose}</td><td className={c.status === "SET" ? "gain" : "muted"}>{c.status === "SET" ? "✓ SET" : "NOT SET"}</td></tr>))}
          </tbody></table>
        <p className="muted">Values are read from environment variables and never shown or stored.</p>
        <h2>Data sources</h2><p>{data.providers.map((p) => feedName(p)).join(", ")}</p>
      </section>
      <section className="panel"><h2>Account</h2>
        <dl className="facts">
          <dt>Venue</dt><dd>{data.venue}</dd>
          <dt>Mode</dt><dd>{MODE_LABELS[data.mode] ?? data.mode}</dd>
          <dt>Live trading</dt><dd>{data.live_trading}</dd>
          <dt>Monthly cost (USD)</dt><dd>{data.monthly_cost_usd}</dd>
          {mode === "advanced" && <><dt>Configuration version</dt><dd>{data.config_version}</dd></>}
        </dl>
        <h2>Accessibility</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>Light theme</button>
          <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>Dark theme</button>
          <button className={guide ? "active" : ""} onClick={() => setGuide(!guide)}>{guide ? "Guide mode on" : "Guide mode off"}</button>
        </div>
        <p className="muted">Gain and loss always carry a sign or arrow beside the color. Both themes use solid surfaces only.</p>
      </section>
    </div>
  );
}
