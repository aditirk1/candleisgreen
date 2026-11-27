// Command bar. Coded commands such as "NVDA NEWS", "RULES" or "KILL", plus plain phrases
// such as "show nvda news" or "why didn't we buy aapl", mapped to the same actions.
export type Command =
  | { screen: string; symbol?: string; topic?: string }
  | { action: "kill" | "theme"; value?: string }
  | { error: string };

const SCREEN_WORDS: Record<string, string> = {
  OVERVIEW: "overview", OPPORTUNITIES: "opportunities", OPP: "opportunities", EXECUTION: "execution", ORDERS: "execution",
  REASONING: "reasoning", WHY: "reasoning", RESEARCH: "research", COMPOSITE: "composite", MARKETS: "markets", NEWS: "news",
  EARNINGS: "earnings", EARN: "earnings", EXPERTS: "experts", BACKTEST: "backtests", BACKTESTS: "backtests", LEARN: "learn",
  GLOBAL: "global", RULES: "rules", AUDIT: "rules", SETTINGS: "settings", CHART: "markets", GP: "markets",
};
const TICKER = /^[A-Z][A-Z0-9.]{0,9}$/;

export function parseCommand(raw: string): Command {
  const text = raw.trim().replace(/[?.!]+$/, "");
  if (!text) return { error: "Empty command" };
  const up = text.toUpperCase();
  const words = up.split(/\s+/);
  if (up === "KILL") return { action: "kill" };
  if (words[0] === "THEME" && (words[1] === "TERMINAL" || words[1] === "GLASS")) return { action: "theme", value: words[1].toLowerCase() };

  // Plain phrases
  let m = up.match(/^WHY (?:DID ?N[O']?T|DIDN'T|NOT) WE (?:BUY|SELL|TRADE) ([A-Z0-9.]+)$/) ?? up.match(/^WHY NOT ([A-Z0-9.]+)$/);
  if (m) return { screen: "reasoning", symbol: m[1] };
  m = up.match(/^(?:SHOW|OPEN|GET)\s+(?:ME\s+)?(?:THE\s+)?([A-Z0-9.]+)\s+(NEWS|EARNINGS|EARN|CHART|REASONING)$/);
  if (m) return { screen: SCREEN_WORDS[m[2]], symbol: m[1] };
  m = up.match(/^(?:SHOW|OPEN|GO TO)\s+(?:ME\s+)?(?:THE\s+)?([A-Z ]+?)(?:\s+SCREEN)?$/);
  if (m && SCREEN_WORDS[m[1].replace(/\s+/g, "")]) return { screen: SCREEN_WORDS[m[1].replace(/\s+/g, "")] };

  // Coded commands
  if (words.length === 1 && SCREEN_WORDS[words[0]]) return { screen: SCREEN_WORDS[words[0]] };
  if (words.length >= 2 && (words[0] === "RESEARCH" || words[0] === "BACKTEST")) return { screen: SCREEN_WORDS[words[0]], topic: words.slice(1).join(" ") };
  if (words.length === 2 && TICKER.test(words[0]) && SCREEN_WORDS[words[1]]) return { screen: SCREEN_WORDS[words[1]], symbol: words[0] };
  if (words.length === 1 && TICKER.test(words[0])) return { screen: "markets", symbol: words[0] };
  return { error: `Unknown command ${text}` };
}
