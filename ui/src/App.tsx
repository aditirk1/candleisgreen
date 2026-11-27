import { FormEvent, useCallback, useEffect, useState } from "react";
import { getJSON, post, Status } from "./api";
import { MODE_LABELS, timeET } from "./format";
import { parseCommand } from "./commands";
import { EXPLAIN, GuideContext } from "./guide";
import { StockContext } from "./stock";
import { StockPanel } from "./screens/StockPanel";
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
const GROUPS: [string, [Screen, string][]][] = [
  ["Today", [["overview", "Overview"], ["news", "News"]]],
  ["Trade", [["opportunities", "Opportunities"], ["execution", "Execution"], ["reasoning", "Reasoning"]]],
  ["Markets", [["markets", "Markets"], ["earnings", "Earnings"], ["global", "Global"]]],
  ["Research", [["research", "Research"], ["composite", "Composite"], ["backtests", "Backtests"], ["experts", "Experts"]]],
  ["Learn", [["learn", "Learn"]]],
  ["System", [["rules", "Audit and Rules"], ["settings", "Settings"]]],
];
const ALL = GROUPS.flatMap(([, s]) => s);
const TOUR: [Screen, string][] = [["overview", "Overview shows account value, the change since the last decision, risk in use, and what is planned for the next session."], ["opportunities", "Opportunities lists what the models propose. Click a row to see the evidence."], ["execution", "Execution is where you approve or reject proposals and see fills."], ["news", "News shows each story with a short summary, why it may matter and what prices did."]];
export type Theme = "light" | "glass" | "terminal";
const THEMES: [Theme, string][] = [["light", "Light"], ["glass", "Dark"], ["terminal", "Terminal"]];

function load(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function save(key: string, v: string) { try { localStorage.setItem(key, v); } catch { /* storage unavailable */ } }
function systemTheme(): Theme { try { return matchMedia("(prefers-color-scheme: dark)").matches ? "glass" : "light"; } catch { return "light"; } }

export function App() {
  const [screen, setScreen] = useState<Screen>(() => (ALL.some(([s]) => `#${s}` === location.hash) ? (location.hash.slice(1) as Screen) : "overview"));
  const [theme, setTheme] = useState<Theme>(() => (load("theme") as Theme) || systemTheme());
  const [guide, setGuide] = useState<boolean>(() => { const g = load("guide"); return g === null ? theme !== "terminal" : g === "on"; });
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [focusClaim, setFocusClaim] = useState<string | null>(null);
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [stock, setStock] = useState<string | null>(null);
  const [cmd, setCmd] = useState("");
  const [cmdMsg, setCmdMsg] = useState<string | null>(null);
  const [explain, setExplain] = useState(false);
  const [tour, setTour] = useState<number | null>(() => (load("toured") ? null : 0));
  const [menu, setMenu] = useState(false);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => { document.documentElement.dataset.theme = theme; save("theme", theme); }, [theme]);
  useEffect(() => { save("guide", guide ? "on" : "off"); }, [guide]);
  useEffect(() => { location.hash = screen; setExplain(false); setMenu(false); }, [screen]);
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
      else setTheme(c.value === "terminal" ? "terminal" : "glass");
      setCmdMsg(null); setCmd(""); return;
    }
    if (c.screen === "markets" && c.symbol && !c.topic) { setStock(c.symbol); setCmd(""); setCmdMsg(null); return; }
    go(c.screen as Screen, c.symbol);
    setCmdMsg(c.topic ? `${c.screen} for ${c.topic}` : null);
    setCmd("");
  }
  function endTour() { setTour(null); save("toured", "1"); }
  function nextTour() {
    if (tour === null) return;
    if (tour + 1 >= TOUR.length) { endTour(); return; }
    setTour(tour + 1); setScreen(TOUR[tour + 1][0]);
  }
  const problems = status ? [
    status.feed.status !== "OK" ? `Feed ${status.feed.status}` : null,
    status.risk_service.status !== "OK" ? `Risk service ${status.risk_service.status}` : null,
    error ? "API error" : null,
  ].filter(Boolean) as string[] : [];
  const health = status ? `Mode ${MODE_LABELS[status.mode] ?? status.mode}. Feed ${status.feed.status}. Risk service ${status.risk_service.status}. API ${error ? "ERROR" : status.api}.` : "";

  return (
    <GuideContext.Provider value={guide}>
      <StockContext.Provider value={{ open: (s) => setStock(s.toUpperCase()) }}>
        <div className="shell">
          <header className="topbar" role="banner">
            <span className="badge venue">{status?.venue ?? "SIMULATION"}</span>
            <span className="muted small">{status ? MODE_LABELS[status.mode] ?? status.mode : ""}</span>
            <span className="muted small">{timeET(status?.now)}</span>
            <span className={problems.length ? "chip warn" : "chip ok"} title={health} aria-label="System status">
              {problems.length ? `▲ ${problems.join(", ")}` : "✓ Systems OK"}
            </span>
            <form className="cmd" onSubmit={runCommand}>
              <input aria-label="Command" className="field" placeholder="Search a ticker or type a command, for example UPCO NEWS" value={cmd} onChange={(e) => setCmd(e.target.value)} />
            </form>
            <button onClick={() => setGuide(!guide)} aria-pressed={guide} className={guide ? "active" : ""}>{guide ? "GUIDE ON" : "GUIDE OFF"}</button>
            <label className="small muted">Theme{" "}
              <select aria-label="Theme" className="field" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
                {THEMES.map(([t, l]) => <option key={t} value={t}>{l}</option>)}
              </select>
            </label>
            <button className={engaged ? "danger engaged" : "danger"} onClick={() => setKill(!engaged)}>
              {engaged ? "KILL SWITCH ON. Release" : "KILL"}
            </button>
          </header>
          {(error || cmdMsg) && <div className="notice" role={error ? "alert" : "status"}>{error ?? cmdMsg}</div>}
          <button className="menu-toggle" onClick={() => setMenu(!menu)} aria-expanded={menu}>Menu</button>
          <nav className={menu ? "sidebar open" : "sidebar"} aria-label="Screens">
            {GROUPS.map(([g, items]) => (
              <div key={g} className="group">
                <div className="group-label">{g}</div>
                {items.map(([s, label]) => <button key={s} className={screen === s ? "active" : ""} aria-current={screen === s ? "page" : undefined} onClick={() => go(s)}>{label}</button>)}
              </div>))}
          </nav>
          <main>
            {tour !== null && TOUR[tour][0] === screen && (
              <div className="tour" role="dialog" aria-label="First-run tour">
                <span><strong>Tour {tour + 1} of {TOUR.length}.</strong> {TOUR[tour][1]}</span>
                <span className="spacer" />
                <button onClick={nextTour}>{tour + 1 >= TOUR.length ? "Finish" : "Next"}</button>
                <button onClick={endTour}>Skip tour</button>
              </div>)}
            {guide && <div className="explain-row"><button className="link" onClick={() => setExplain(!explain)}>{explain ? "Hide explanation" : "Explain this screen"}</button></div>}
            {explain && <div className="panel explain" aria-label="Screen explanation"><h2>About this screen</h2>{(EXPLAIN[screen] ?? []).map((l, i) => <p key={i}>{l}</p>)}</div>}
            {screen === "overview" && <OverviewScreen tick={tick} onGo={(s) => go(s as Screen)} />}
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
          {stock && <StockPanel symbol={stock} tick={tick} onClose={() => setStock(null)} onGo={(s, sym) => { setStock(null); go(s as Screen, sym); }} />}
        </div>
      </StockContext.Provider>
    </GuideContext.Provider>
  );
}
