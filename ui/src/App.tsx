import { useCallback, useEffect, useState } from "react";
import { getJSON, post, Status } from "./api";
import { timeET } from "./format";
import { OverviewScreen } from "./screens/Overview";
import { ExecutionScreen } from "./screens/Execution";
import { EarningsScreen } from "./screens/Earnings";
import { ResearchScreen } from "./screens/Research";
import { CompositeScreen } from "./screens/Composite";
import { NewsScreen } from "./screens/News";
import { ReasoningScreen } from "./screens/Reasoning";
import { LearnScreen } from "./screens/Learn";
import { GlobalScreen } from "./screens/Global";

type Screen = "overview" | "execution" | "earnings" | "research" | "composite" | "news" | "reasoning" | "learn" | "global";
const SCREENS: [Screen, string][] = [["overview", "Overview"], ["execution", "Execution"], ["reasoning", "Reasoning"], ["research", "Research"], ["composite", "Composite"], ["news", "News"], ["earnings", "Earnings"], ["global", "Global"], ["learn", "Learn"]];

const MODE_LABELS: Record<string, string> = {
  research: "Research", teaching: "Teaching and market watch", manual_simulation: "Manual simulation",
  auto_simulation: "Auto simulation", broker_paper_approval: "Broker paper, approval", broker_paper_auto: "Broker paper, auto",
};
type Theme = "terminal" | "glass";

export function App() {
  const [screen, setScreen] = useState<Screen>(() => (SCREENS.some(([s]) => `#${s}` === location.hash) ? (location.hash.slice(1) as Screen) : "overview"));
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem("theme") as Theme) || "terminal");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [focusClaim, setFocusClaim] = useState<string | null>(null);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("theme", theme); }, [theme]);
  useEffect(() => { location.hash = screen; }, [screen]);
  useEffect(() => {
    getJSON<Status>("/api/status").then((s) => { setStatus(s); setError(null); }).catch((e) => setError(String(e)));
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [tick, refresh]);

  const engaged = status?.risk_service.kill_switch === true;
  async function toggleKill() {
    const r = await post("/api/kill-switch", { engaged: !engaged });
    if (!r.ok) setError(`Kill switch not confirmed by the risk service (${r.status})`);
    refresh();
  }

  return (
    <>
      <div className="strip" role="banner">
        <span className="badge venue">{status?.venue ?? "SIMULATION"}</span>
        <span className="badge">Mode {status ? MODE_LABELS[status.mode] ?? status.mode : "NOT AVAILABLE"}</span>
        <span className="badge">Account simulator</span>
        <span className="badge">Time {timeET(status?.now)}</span>
        <span className="badge">Feed {status?.feed.status ?? "NOT AVAILABLE"}</span>
        <span className="badge">Risk service {status?.risk_service.status ?? "NOT AVAILABLE"}</span>
        <span className="badge">API {error ? "ERROR" : status?.api ?? "NOT AVAILABLE"}</span>
        <span className="spacer" />
        <button onClick={() => setTheme(theme === "terminal" ? "glass" : "terminal")}>
          {theme === "terminal" ? "THEME GLASS" : "THEME TERMINAL"}
        </button>
        <button className={engaged ? "danger engaged" : "danger"} onClick={toggleKill}>
          {engaged ? "KILL SWITCH ON. Release" : "KILL"}
        </button>
      </div>
      {error && <div className="panel loss" role="alert">{error}</div>}
      <nav className="nav">
        {SCREENS.map(([s, label]) => <button key={s} className={screen === s ? "active" : ""} onClick={() => setScreen(s)}>{label}</button>)}
      </nav>
      <main>
        {screen === "overview" && <OverviewScreen tick={tick} />}
        {screen === "execution" && <ExecutionScreen tick={tick} onChange={refresh} />}
        {screen === "earnings" && <EarningsScreen tick={tick} />}
        {screen === "research" && <ResearchScreen tick={tick} focus={focusClaim} />}
        {screen === "news" && <NewsScreen tick={tick} />}
        {screen === "reasoning" && <ReasoningScreen tick={tick} />}
        {screen === "learn" && <LearnScreen tick={tick} />}
        {screen === "global" && <GlobalScreen tick={tick} />}
        {screen === "composite" && <CompositeScreen tick={tick} onEvidence={(id) => { setFocusClaim(id); setScreen("research"); }} />}
      </main>
    </>
  );
}
