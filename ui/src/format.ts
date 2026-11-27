// Formatting rules: 24-hour times with zone, ISO dates, units in headers, signs beside colors.
const TZ = "America/New_York";

export function timeET(iso: string | null | undefined): string {
  if (!iso) return "NOT AVAILABLE";
  const d = new Date(iso);
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const time = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
  return `${date} ${time} ET`;
}

export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined) return "NOT AVAILABLE";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function pct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "NOT AVAILABLE";
  return `${(n * 100).toFixed(digits)}`;
}

export function signed(n: number | null | undefined, f: (x: number) => string): { text: string; cls: string } {
  if (n === null || n === undefined) return { text: "NOT AVAILABLE", cls: "na" };
  if (n > 0) return { text: `▲ +${f(n)}`, cls: "gain" };
  if (n < 0) return { text: `▼ ${f(n)}`, cls: "loss" };
  return { text: `${f(n)}`, cls: "" };
}

export const MODE_LABELS: Record<string, string> = {
  research: "Research", teaching: "Teaching and market watch", manual_simulation: "Manual simulation",
  auto_simulation: "Auto simulation", broker_paper_approval: "Broker paper, approval", broker_paper_auto: "Broker paper, auto",
};

const SIDES: Record<string, string> = { buy: "▲ Buy", sell: "▼ Sell", sell_short: "▼ Sell short", buy_to_cover: "▲ Buy to cover" };
export function sideLabel(side: string): string { return SIDES[side] ?? side; }
