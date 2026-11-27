// Guide mode: plain labels with the technical term on hover, metric cards, and screen walkthroughs.
// Guide mode never hides risk warnings, the venue label or the kill switch.
import { createContext, ReactNode, useContext } from "react";
import glossaryFile from "../../config/glossary.json";

export const GuideContext = createContext(false);

type Entry = { plain: string; meaning: string; formula?: string; typical?: string };

// Locked definitions. Formulas match the code that computes each value.
// Locked definitions live in config/glossary.json, shared with the spaced review deck.
export const GLOSSARY: Record<string, Entry> = glossaryFile.terms;

export function Term({ k, children }: { k: string; children: ReactNode }) {
  const guide = useContext(GuideContext);
  const e = GLOSSARY[k];
  if (!e) return <>{children}</>;
  const card = [e.meaning, e.formula ? `Formula: ${e.formula}` : null, e.typical ? `Typical range: ${e.typical}` : null].filter(Boolean).join("\n");
  return <span title={card} className="term">{guide ? <>{e.plain} ({children})</> : children}</span>;
}

export const EXPLAIN: Record<string, string[]> = {
  overview: ["The three numbers at the top are account value, the change since the last decision, and how much of the account is invested.", "Next session plan lists what the models propose for the next trading day. In manual mode nothing trades until you approve it on Execution.", "Click any ticker to see what the company is, what its price did and what the system thinks of it."],
  opportunities: ["Each row is a proposal from the last decision run for the next session.", "Expected return stays NOT AVAILABLE until a model is calibrated, so only direction and rank are used.", "The risk column is the first line of the model's reason. The risk service checks every order again at execution."],
  reasoning: ["Type a ticker to see the forecast, the risk verdict, which Composite signals agree or oppose, and recent news.", "Why not explains an abstention or a veto from recorded facts only."],
  execution: ["Approve or reject proposals in the queue. Approved orders go to the simulator as limit orders in the execution window.", "Fills show slippage against the quote midpoint at arrival. Reconciliation compares the journal with the broker."],
  research: ["Claim cards show each research claim by status with its evidence chain.", "The failure archive keeps negative results visible so they count against the trial total."],
  composite: ["Each signal shows its tier, three scores and capital weight. Exclusion reasons show the parameter and its basis.", "Results are RETROSPECTIVE until prospective forecasts exist."],
  markets: ["Search an instrument to see its recorded closes, tag, sector and Composite score.", "Instruments tagged research_only can never receive orders."],
  company: ["The top says whether the system would trade the company and why, in plain words.", "Every figure shows its source, the period it measures and how many days old it is. A figure without a source reads NOT AVAILABLE with the reason.", "The business description is the SEC industry code. The revenue model and the 10-K risk factors are not parsed yet."],
  news: ["Each card is one story from an official source, with repeats merged. Click it to open three parts.", "What happened is the source's own summary. Why it may matter is a general description of that kind of news, not a forecast.", "What prices did shows the next recorded close for each named company beside all recorded stocks. It is an observation, not proof of cause."],
  earnings: ["Figures come from SEC filings with a link to each one. Beat or miss never appears because no consensus estimate is recorded."],
  experts: ["Every data source with its license and what it may be used for.", "Practitioner claims need 30 scored claims in a domain before they can become a signal."],
  backtests: ["Each row is a signal's walk-forward research portfolio after costs. The trial count sits beside every result."],
  global: ["Sessions, FX from FRED and the data entitlement map. Non-US instruments are research only."],
  learn: ["Replay a past session with only what was known then, make a prediction, then reveal the outcome."],
  rules: ["The audit log is hash-chained. A break in the chain shows here at once.", "Hard limits: a tighter value applies now. A looser value waits and needs a second confirmation. Only Aditi can change them.", "Every config value shows its basis."],
  settings: ["Credentials show SET or NOT SET only. Values never leave the environment.", "Monthly cost is 0 USD by rule."],
};
