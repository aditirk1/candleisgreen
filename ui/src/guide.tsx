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
  overview: ["The three numbers at the top are account value, the change since the last decision, and how much of the account is invested.", "The equity curve is the simulator account value after each decision run.", "Alerts are one line each: ticker, event, time. Positions are priced from the last recorded close."],
  opportunities: ["Each row is a proposal from the last decision run for the next session.", "Expected return stays NOT AVAILABLE until a model is calibrated, so only direction and rank are used.", "The risk column is the first line of the model's reason. The risk service checks every order again at execution."],
  reasoning: ["Type a ticker to see the forecast, the risk verdict, which Composite signals agree or oppose, and recent news.", "Why not explains an abstention or a veto from recorded facts only."],
  execution: ["Approve or reject proposals in the queue. Approved orders go to the simulator as limit orders in the execution window.", "Fills show slippage against the quote midpoint at arrival. Reconciliation compares the journal with the broker."],
  research: ["Claim cards show each research claim by status with its evidence chain.", "The failure archive keeps negative results visible so they count against the trial total."],
  composite: ["Each signal shows its tier, three scores and capital weight. Exclusion reasons show the parameter and its basis.", "Results are RETROSPECTIVE until prospective forecasts exist."],
  markets: ["Search an instrument to see its recorded closes, tag, sector and Composite score.", "Instruments tagged research_only can never receive orders."],
  news: ["Stories are clustered from official feeds. What prices did is kept on the Reasoning screen, apart from what happened."],
  earnings: ["Figures come from SEC filings with a link to each one. Beat or miss never appears because no consensus estimate is recorded."],
  experts: ["Every data source with its license and what it may be used for.", "Practitioner claims need 30 scored claims in a domain before they can become a signal."],
  backtests: ["Each row is a signal's walk-forward research portfolio after costs. The trial count sits beside every result."],
  global: ["Sessions, FX from FRED and the data entitlement map. Non-US instruments are research only."],
  learn: ["Replay a past session with only what was known then, make a prediction, then reveal the outcome."],
  rules: ["The audit log is hash-chained. A break in the chain shows here at once.", "Hard limits: a tighter value applies now. A looser value waits and needs a second confirmation. Only Aditi can change them.", "Every config value shows its basis."],
  settings: ["Credentials show SET or NOT SET only. Values never leave the environment.", "Monthly cost is 0 USD by rule."],
};
