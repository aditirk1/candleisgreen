import { FormEvent, useCallback, useEffect, useState } from "react";
import { getJSON, post, Status } from "./api";
import { MODE_LABELS, timeET } from "./format";
import { parseCommand } from "./commands";
import { EXPLAIN, GuideContext } from "./guide";
import { OverviewScreen } from "./screens/Overview";
import { OpportunitiesScreen } from "./screens/Opportunities";
import { ExecutionScreen } from "./screens/Execution";
import { EarningsScreen } from "./screens/Earnings";
import { ResearchScreen } from "./screens/Research";
import { CompositeScreen } from "./screens/Composite";
import { NewsScreen } from "./screens/News";
import { ReasoningScreen } from "./screens/Reasoning";
import { LearnScreen } from "./screens/Learn";
import { GlobalScreen } from "./screens/Global";
import { MarketsScreen } from "./screens/Markets";
import { ExpertsScreen } from "./screens/Experts";
import { BacktestsScreen } from "./screens/Backtests";
import { RulesScreen } from "./screens/Rules";
import { SettingsScreen } from "./screens/Settings";

type Screen = "overview" | "opportunities" | "execution" | "reasoning" | "research" | "composite" | "markets" | "news" | "earnings" | "experts" | "backtests" | "learn" | "global" | "rules" | "settings";
const SCREENS: [Screen, string][] = [["overview", "Overview"], ["opportunities", "Opportunities"], ["reasoning", "Reasoning"], ["execution", "Execution"], ["research", "Research"], ["composite", "Composite"], ["markets", "Markets"], ["news", "News"], ["earnings", "Earnings"], ["experts", "Experts"], ["backtests", "Backtests"], ["learn", "Learn"], ["global", "Global"], ["rules", "Audit and Rules"], ["settings", "Settings"]];
const TOUR: [Screen, string][] = [["overview", "Overview shows account value, the change since the last decision and risk in use."], ["opportunities", "Opportunities lists what the models propose for the next session, with evidence on the right."], ["execution", "Execution is where you approve or reject proposals and see fills."], ["research", "Research holds every claim, its evidence and the failures."]];

type Theme = "terminal" | "glass";

function load(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function save(key: string, v: string) { try { localStorage.setItem(key, v); } catch { /* storage unavailable */ } }

export function App() {
  const [screen, setScreen] = useState<Screen>(() => (SCREENS.some(([s]) => `#${s}` === location.hash) ? (location.hash.slice(1) as Screen) : "overview"));
  const [theme, setTheme] = useState<Theme>(() => (load("theme") as Theme) || "terminal");
  const [guide, setGuide] = useState<boolean>(() => { const g = load("guide"); return g === null ? theme === "glass" : g === "on"; });
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [focusClaim, setFocusClaim] = useState<string | null>(null);
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [cmd, setCmd] = useState("");
  const [cmdMsg, setCmdMsg] = useState<string | null>(null);
  const [explain, setExplain] = useState(false);
  const [tour, setTour] = useState<number | null>(() => (load("toured") ? null : 0));

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => { document.documentElement.dataset.theme = theme; save("theme", theme); }, [theme]);
  useEffect(() => { save("guide", guide ? "on" : "off"); }, [guide]);
  useEffect(() => { location.hash = screen; setExplain(false); }, [screen]);
  useEffect(() => {
    getJSON<Status>("/api/status").then((s) => { setStatus(s); setError(null); }).catch((e) => setError(String(e)));
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [tick, refresh]);

  const engaged = status?.risk_service.kill_switch === true;
  async function setKill(on: boolean) {
    const r = await post("/api/kill-switch", { engaged: on });
    if (!r.ok) setError(`Kill switch not confirmed by the risk service (${r.status})`);
    refresh();
  }
  function go(s: Screen, sym?: string) { setSymbol(sym); setScreen(s); }
  function runCommand(e: FormEvent) {
    e.preventDefault();
    const c = parseCommand(cmd);
    if ("error" in c) { setCmdMsg(c.error); return; }
    if ("action" in c) {
      if (c.action === "kill") setKill(true);
      else setTheme(c.value as Theme);
      setCmdMsg(null); setCmd(""); return;
    }
    go(c.screen as Screen, c.symbol);
    setCmdMsg(c.topic ? `${c.screen} for ${c.topic}` : null);
    setCmd("");
  }
  function nextTour() {
    if (tour === null) return;
    if (tour + 1 >= TOUR.length) { setTour(null); save("toured", "1"); return; }
    setTour(tour + 1); setScreen(TOUR[tour + 1][0]);
  }

  return (
    <GuideContext.Provider value={guide}>
      <div className="strip" role="banner">
        <span className="badge venue">{status?.venue ?? "SIMULATION"}</span>
        <span className="badge">Mode {status ? MODE_LABELS[status.mode] ?? status.mode : "NOT AVAILABLE"}</span>
        <span className="badge">Account simulator</span>
        <span className="badge">Time {timeET(status?.now)}</span>
        <span className="badge">Feed {status?.feed.status ?? "NOT AVAILABLE"}</span>
        <span className="badge">Risk service {status?.risk_service.status ?? "NOT AVAILABLE"}</span>
        <span className="badge">API {error ? "ERROR" : status?.api ?? "NOT AVAILABLE"}</span>
        <span className="spacer" />
        <button onClick={() => setGuide(!guide)} aria-pressed={guide}>{guide ? "GUIDE ON" : "GUIDE OFF"}</button>
        <button onClick={() => setTheme(theme === "terminal" ? "glass" : "terminal")}>
          {theme === "terminal" ? "THEME GLASS" : "THEME TERMINAL"}
        </button>
        <button className={engaged ? "danger engaged" : "danger"} onClick={() => setKill(!engaged)}>
          {engaged ? "KILL SWITCH ON. Release" : "KILL"}
        </button>
      </div>
      {error && <div className="panel loss" role="alert">{error}</div>}
      <form className="cmd" onSubmit={runCommand}>
        <input aria-label="Command" className="field" placeholder="Command, for example UPCO NEWS, RULES, why didn't we buy UPCO" value={cmd} onChange={(e) => setCmd(e.target.value)} />
        <button type="submit">Go</button>
        {guide && <button type="button" onClick={() => setExplain(!explain)}>Explain this screen</button>}
        {cmdMsg && <span className="muted" role="status">{cmdMsg}</span>}
      </form>
      <nav className="nav">
        {SCREENS.map(([s, label]) => <button key={s} className={screen === s ? "active" : ""} onClick={() => go(s)}>{label}</button>)}
      </nav>
      {tour !== null && (
        <div className="panel tour" role="dialog" aria-label="First-run tour">
          <strong>Tour {tour + 1} of {TOUR.length}.</strong> {TOUR[tour][1]}
          <span className="spacer" />
          <button onClick={nextTour}>{tour + 1 >= TOUR.length ? "Finish" : "Next"}</button>
          <button onClick={() => { setTour(null); save("toured", "1"); }}>Skip tour</button>
        </div>)}
      {explain && <div className="panel explain" aria-label="Screen explanation"><h2>About this screen</h2>{(EXPLAIN[screen] ?? []).map((l, i) => <p key={i}>{l}</p>)}</div>}
      <main>
        {screen === "overview" && <OverviewScreen tick={tick} />}
        {screen === "opportunities" && <OpportunitiesScreen tick={tick} onReason={(s) => go("reasoning", s)} />}
        {screen === "execution" && <ExecutionScreen tick={tick} onChange={refresh} />}
        {screen === "earnings" && <EarningsScreen tick={tick} ticker={symbol} />}
        {screen === "research" && <ResearchScreen tick={tick} focus={focusClaim} />}
        {screen === "news" && <NewsScreen tick={tick} ticker={symbol} />}
        {screen === "reasoning" && <ReasoningScreen tick={tick} initial={symbol} />}
        {screen === "learn" && <LearnScreen tick={tick} />}
        {screen === "global" && <GlobalScreen tick={tick} />}
        {screen === "markets" && <MarketsScreen tick={tick} initial={symbol} />}
        {screen === "experts" && <ExpertsScreen tick={tick} />}
        {screen === "backtests" && <BacktestsScreen tick={tick} />}
        {screen === "rules" && <RulesScreen tick={tick} onChange={refresh} />}
        {screen === "settings" && <SettingsScreen tick={tick} theme={theme} setTheme={setTheme} guide={guide} setGuide={setGuide} />}
        {screen === "composite" && <CompositeScreen tick={tick} onEvidence={(id) => { setFocusClaim(id); setScreen("research"); }} />}
      </main>
    </GuideContext.Provider>
  );
}
