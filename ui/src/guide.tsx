// Guide mode: plain labels with the technical term on hover, metric cards, and screen walkthroughs.
// Guide mode never hides risk warnings, the venue label or the kill switch.
import { createContext, ReactNode, useContext } from "react";

export const GuideContext = createContext(false);

type Entry = { plain: string; meaning: string; formula?: string; typical?: string };

// Locked definitions. Formulas match the code that computes each value.
export const GLOSSARY: Record<string, Entry> = {
  alpha: { plain: "Expected gain", meaning: "Return the model expects beyond what the market and known factors explain", formula: "alpha = E[r] minus beta times market return", typical: "A few tenths of a percent a month is already large" },
  volatility: { plain: "How much it swings", meaning: "Standard deviation of returns, scaled to a year", formula: "sigma_annual = sigma_daily times sqrt(252)", typical: "Large US stocks 15 to 40 percent a year" },
  prob_positive: { plain: "Chance the edge is real", meaning: "Posterior probability that the signal's true mean return is above zero after shrinkage", formula: "P = Phi(mu_hat / se)", typical: "Above 0.9 is strong. Near 0.5 means no information" },
  sharpe: { plain: "Return per unit of swing", meaning: "Mean excess return divided by its standard deviation, annualized", formula: "SR = mean / sd times sqrt(12) for monthly data", typical: "0.5 is decent for one signal. Above 2 usually means an error or overfitting" },
  trial_count: { plain: "How many versions were tried", meaning: "Every variant tested, kept or not. More trials make a lucky result more likely", typical: "Compare a Sharpe ratio with this number before trusting it" },
  slippage_bps: { plain: "Price paid versus the midpoint", meaning: "Fill price compared with the quote midpoint at arrival, in basis points", formula: "side times (fill minus mid) / mid times 10000", typical: "Liquid US stocks 1 to 10" },
  signal_strength: { plain: "How strongly the model leans", meaning: "Model output before calibration. It is not a probability or a forecast return", typical: "Only the sign and rank are used until calibration exists" },
  tier: { plain: "How much evidence", meaning: "Evidence tier from 1 (idea) to 6. Academic evidence stops at 3. Tier 4 needs a test on real data. Tier 5 needs prospective results and Aditi", typical: "Only tiers 4 and up can carry capital" },
  economic: { plain: "Worth trading after costs", meaning: "Result of the walk-forward research portfolio at double the modeled costs" },
  basis: { plain: "Why this number", meaning: "Empirical comes from a cited result. Safeguard limits damage and only Aditi changes it. Provisional is a starting setting under review. External fact has a source and a date" },
  adv20: { plain: "Normal daily trading", meaning: "Average dollar volume over the last 20 sessions", typical: "Orders here stay under a small share of it" },
};

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
