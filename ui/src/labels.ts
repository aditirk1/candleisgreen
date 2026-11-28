// Display names. The backend speaks in identifiers. People read these names instead.
// Anything missing from a map falls back to humanize(), so no code-style name reaches the screen.
import { timeET } from "./format";

const SIGNALS: Record<string, string> = {
  ts_momentum_252_21: "Trend model, 12-month price trend",
  xs_momentum_12_1: "Momentum, 12-month winners against losers",
  st_reversal_5: "Short-term reversal, last week's losers",
  betting_against_beta: "Low-risk stocks (betting against beta)",
  level_a_momentum_ols: "Model A, simple trend regression",
  level_b_ridge: "Model B, ridge regression",
  level_c_gbt: "Model C, boosted decision trees",
  fixture_baseline: "Test model",
  Mom12m: "Momentum, 12 months",
  STreversal: "Short-term reversal",
  BetaFP: "Low-risk stocks (betting against beta)",
};
const FAMILIES: Record<string, string> = { momentum: "Momentum", short_term_reversal: "Short-term reversal", trend: "Trend", low_risk: "Low risk" };
const VENDORS: Record<string, string> = {
  alpaca_synthetic: "Demo data (invented prices)", alpaca: "Alpaca market data", sec: "SEC filings", fred: "FRED, Federal Reserve Bank of St. Louis",
  fixture: "Test data", test: "Test data",
};
const LICENSES: Record<string, string> = {
  synthetic: "Invented test data", cc_by_4_0: "Creative Commons, free to use with credit", cc_by_nc_4_0: "Creative Commons, non-commercial use only",
  french_library: "Kenneth French data library", alpaca_market_data: "Alpaca market data, for the account holder", us_government_public: "US government public data",
  fred_terms: "FRED terms of use", user_capture: "Material you pasted in", clinicaltrials_gov: "ClinicalTrials.gov",
};
const FEEDS: Record<string, string> = { fed_press: "Federal Reserve press releases", sec_press: "SEC press releases", sec_litigation: "SEC litigation releases" };
const LIMITS: Record<string, string> = {
  max_position_pct_equity: "Largest position, share of account",
  max_cluster_pct_equity: "Largest group of similar stocks, share of account",
  max_order_pct_adv20: "Largest order, share of normal daily trading",
  max_spread_pct: "Widest bid-ask spread allowed",
  daily_loss_stop_pct_equity: "Daily loss that stops new trades",
  max_quote_age_seconds: "Oldest price quote allowed, seconds",
  max_short_position_pct_equity: "Largest short position, share of account",
  max_short_exposure_pct_equity: "All short positions together, share of account",
  max_gross_exposure_pct_equity: "Long plus short positions, share of account",
};
const EVENTS: Record<string, string> = {
  promotion_proposed: "Promotion proposed", promotion_decided: "Promotion decided", experiment_registered: "Test registered in advance",
  experiment_completed: "Test completed", variant_recorded: "Test version recorded", claim_extracted: "Research claim recorded",
  claim_status: "Claim status changed", reevaluation_opened: "Review of a signal opened", evidence_link: "Evidence linked",
  signal_tier: "Evidence level changed", forecast_issued: "Forecast made", proposal_created: "Trade proposed", proposal_approved: "Trade approved",
  proposal_rejected: "Trade rejected", proposal_status: "Trade status changed", order_intent_created: "Order prepared", risk_decision: "Risk check",
  fill: "Order filled", reconciliation: "Account check against the broker", kill_switch: "Kill switch changed", weights_frozen: "Signal weights fixed",
  limit_change_requested: "Limit change requested", limit_change_confirmed: "Limit change confirmed", no_order: "No order",
};
const PARAMS: Record<string, string> = {
  "composite.eligibility.min_tier": "Minimum evidence level for capital",
  "composite.eligibility.min_oos_days": "Minimum days of out-of-sample testing",
  "composite.promotion.shadow_min_trading_days": "Minimum days of paper record before promotion",
  "composite.promotion.max_tracking_error_annual": "Largest allowed gap between paper and model results",
  "time.market_timezone": "Market time zone", "time.decision_time_local": "Daily decision time", "time.execution_window_start_local": "Order window opens",
  "time.execution_window_end_local": "Order window closes", "time.preopen_check_local": "Pre-open check time",
  "universe.min_price": "Lowest share price to join the list", "universe.min_median_dollar_volume_20d": "Lowest daily trading value to join the list, USD",
  "universe.exit_min_price": "Share price below which a stock leaves the list", "universe.exit_min_median_dollar_volume_20d": "Daily trading value below which a stock leaves the list, USD",
  "universe.dollar_volume_window_days": "Days used to measure trading value", "universe.exclude_leveraged_inverse_etfs": "Leave out leveraged and inverse funds",
  "sizing.max_names": "Most stocks held long at once", "sizing.max_short_names": "Most stocks held short at once",
  "sizing.min_trade_value_usd": "Smallest trade, USD", "sizing.target_weight_per_name": "Target size per stock, share of account",
  "execution.limit_offset_fraction": "Limit price distance from the quote", "execution.live_trading_enabled": "Live trading (always off)",
  "execution.mode": "Trading mode", "execution.order_type": "Order type", "execution.simulator_starting_equity_usd": "Simulator starting balance, USD",
  "risk.hard_limits.execution_grade_feeds": "Price feeds good enough for orders", "risk.loosening_delay_hours": "Wait before a looser limit can be confirmed, hours",
  "markets.sessions_utc.asia_pacific": "Asia Pacific job time (UTC)", "markets.sessions_utc.europe": "Europe job time (UTC)", "markets.sessions_utc.us": "United States job time (UTC)",
  "markets.sessions_utc.overnight_review": "Overnight review time (UTC)", "markets.us_exchanges": "US exchanges traded",
  "news.live_view_hours": "Short news window, hours", "news.recent_view_days": "Long news window, days", "news.cluster_window_hours": "Hours within which reports count as one story",
  "news.cluster_similarity": "How alike two headlines must be to count as one story", "news.max_summary_chars": "Longest summary, characters", "news.feeds": "News sources",
  "models.ts_momentum.lookback_days": "Trend model, days looked back", "models.ts_momentum.skip_days": "Trend model, most recent days skipped", "models.ts_momentum.clip": "Trend model, largest signal allowed",
};
/** Sections of the parameter registry that shape trades directly. The rest tune the research engine and appear in Advanced mode. */
export const EVERYDAY_PARAM_SECTIONS = ["risk.", "sizing.", "universe.", "time.", "execution.", "markets.", "news.", "models."];
/** Settings inside an everyday section that still belong to the research engine. */
export const RESEARCH_PARAM_PREFIXES = ["universe.research_universes."];
const PARAM_SECTIONS: [string, string][] = [
  ["universe.research_universes.biotech.", "Biotech research list"], ["composite.", "Signal combination"], ["research.", "Research"], ["sources.", "Data source"],
  ["clustering.", "Stock groups"], ["teaching.", "Learning"], ["risk.hard_limits.", ""], ["execution.", "Orders"],
];
const WORDS: Record<string, string> = {
  pct: "percent", adv20: "20-day average volume", usd: "USD", min: "minimum", max: "maximum", oos: "out-of-sample", vol: "volatility", var: "variance",
  cov: "covariance", ts: "time series", ic: "forecast accuracy", hrp: "risk-balanced weighting", fdr: "false discovery rate", hac: "HAC", se: "standard error",
  nav: "account value", url: "web address", env: "environment variable", sec: "SEC", finra: "FINRA", taf: "trading activity fee", sic: "industry code",
  osap: "Open Source Asset Pricing", ema: "moving average", sip: "consolidated feed", "13f": "13F", fred: "FRED", alpaca: "Alpaca", oos_days: "out-of-sample days",
  winsor: "trim", n: "number of", lambda: "risk aversion", kappa: "impact", tau: "uncertainty", omega: "uncertainty", alpha: "edge", delta: "shrinkage",
};
const STATUSES: Record<string, string> = {
  EXTRACTED: "Recorded", NEEDS_INPUT: "Needs your input", NEEDS_DATA: "Needs data", REPRODUCED: "Reproduced", FAILED: "Did not hold up", REPLICATED: "Replicated",
  PASSED: "Passed", REGISTERED: "Registered", OPEN: "Open", PENDING: "Waiting", APPROVED: "Approved", DECLINED: "Declined",
  retrospective: "Back-tested", prospective: "Recorded in advance", SIGNAL_STRENGTH_ONLY: "Not calibrated",
};
const TYPES: Record<string, string> = { common_stock: "Common stock", etf: "Exchange-traded fund", adr: "Foreign company share (ADR)", unknown: "Unknown" };
const STUDIES: Record<string, string> = {
  reproduction: "Reproduce the published result", replication: "Test in other markets or years", new_factor: "Test a new idea",
  event_study: "Event study", forecast: "Forecast against a simpler model", economic: "Value after trading costs", needs_plan: "Waiting for a test plan",
};
const DATA_LABELS: Record<string, string> = { SYNTHETIC: "Demo data", "SURVIVORSHIP-BIASED": "Data missing failed companies" };
const CAPABILITIES: Record<string, string> = {
  us_factor_research: "US factor research", global_factor_research: "Global factor research", us_daily_bars: "US daily prices",
  us_stock_history_with_delistings: "US price history including failed companies", us_fundamentals_point_in_time: "US company financials, as known at the time",
  macro: "Economic data", clinical_trials: "Clinical trials", fda_advisory_calendar: "FDA advisory meetings", paper_execution_us: "Paper trading, US stocks",
  realtime_consolidated_quotes: "Real-time quotes from all exchanges", intraday_trading: "Trading during the day", short_selling_us: "Short selling, US stocks",
  options_trading: "Options trading", crypto_trading: "Crypto trading", futures_trading: "Futures trading", fx_rates: "Exchange rates", fx_trading: "Currency trading",
  futures_data: "Futures prices", crypto_data: "Crypto prices", insider_transactions: "Insider trades", institutional_holdings: "Fund holdings (13F)",
  large_holder_filings: "Large shareholder filings", congressional_disclosures: "Trades by members of Congress", government_procurement: "Government contracts",
  regulatory_actions: "Regulatory actions", political_sector_exposure: "Political exposure by industry", options_data_and_flow: "Options prices and activity",
  analyst_consensus_estimates: "Analyst estimates", licensed_news: "Paid news services", non_us_execution: "Trading outside the US", llm_features: "AI language model features",
};
const TAGS: Record<string, string> = { direct: "Tradable", proxy: "Tradable as a stand-in", research_only: "Research only" };

export function humanize(id: string | null | undefined): string {
  if (!id) return "";
  const s = id.replace(/[_.]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
const make = (m: Record<string, string>) => (id: string | null | undefined) => (id ? m[id] ?? m[id.split(" ")[0]] ?? humanize(id) : "");
export const signalName = make(SIGNALS);
export const familyName = make(FAMILIES);
export const vendorName = make(VENDORS);
export const licenseName = make(LICENSES);
export const feedName = make(FEEDS);
export const limitName = make(LIMITS);
export const eventName = make(EVENTS);
export function paramName(path: string | null | undefined): string {
  if (!path) return "";
  if (PARAMS[path]) return PARAMS[path];
  const last = path.split(".").pop() ?? path;
  if (LIMITS[last]) return LIMITS[last];
  const words = last.split("_").map((w) => WORDS[w] ?? w).join(" ");
  const sec = PARAM_SECTIONS.find(([pre]) => path.startsWith(pre));
  const group = sec ? sec[1] : humanize(path.split(".")[0]);
  const name = words.charAt(0).toUpperCase() + words.slice(1);
  return group ? `${group}: ${name.charAt(0).toLowerCase() + name.slice(1)}` : name;
}
export const statusName = make(STATUSES);
export const typeName = make(TYPES);
export const tagName = make(TAGS);
export const capabilityName = make(CAPABILITIES);
export const studyName = make(STUDIES);
export const dataLabel = make(DATA_LABELS);

/** A model reference such as "ts_momentum_252_21 1.0.0" becomes its name. The version is a technical detail. */
export function modelName(ref: string | null | undefined): string { return signalName((ref ?? "").split(" ")[0]); }

const REASONS: [RegExp, string][] = [
  [/result is on SYNTHETIC data and is not evidence/i, "Tested only on demo data, which is not evidence"],
  [/result is SURVIVORSHIP-BIASED and cannot pass any gate/i, "Tested on data that leaves out failed companies, so it cannot count"],
  [/tier (\d) below (\d)/i, "Evidence level $1 of 6. Trading needs level $2"],
  [/no edge estimate/i, "No estimate of its edge yet"],
  [/estimated edge is not positive/i, "Its estimated edge is not positive"],
  [/probability positive ([0-9.]+) below ([0-9.]+)/i, "Chance its edge is real is $1, needs $2"],
  [/(\d+) out-of-sample days below (\d+)/i, "$1 days of out-of-sample testing, needs $2"],
  [/(\d+) events and (\d+) days, need (\d+) events/i, "$1 events over $2 days, needs $3 events"],
  [/data feed is not healthy/i, "The price data feed is not healthy"],
  [/(\d+) shadow days, minimum (\d+)/i, "$1 days of paper record, needs $2"],
  [/,\s*SYNTHETIC/g, ", demo data"], [/,\s*SURVIVORSHIP-BIASED/g, ", data missing failed companies"], [/,\s*RETROSPECTIVE/g, ", back-tested"],
  [/,\s*PROSPECTIVE/g, ", recorded in advance"],
  [/reproduction PASSED/g, "Reproduced the published result"], [/reproduction FAILED/g, "Did not reproduce the published result"],
  [/replication PASSED/g, "Held up in other markets"], [/replication FAILED/g, "Did not hold up in other markets"],
  [/, t ([-0-9.]+)\)/g, ", t-statistic $1)"], [/net at 10% volatility/g, "after costs, scaled to 10% yearly swings"],
  [/90% lower bound/g, "pessimistic case"],
  [/shadow record is retrospective, a prospective record is required/i, "The paper record was made after the fact. It must be recorded in advance"],
  [/loosening waits until/g, "a looser value waits until"],
  [/no vintage stored yet/g, "No published value recorded yet"], [/labeled SURVIVORSHIP-BIASED/g, "labeled as missing failed companies"],
];
const BASIS: [RegExp, string][] = [
  [/\s*SAFEGUARD\s*$/, " (safety rule)"], [/\s*PROVISIONAL\s*$/, " (starting setting, under review)"],
  [/\s*EMPIRICAL \(([^)]*)\)\s*$/, " (from published research)"], [/\s*EXTERNAL FACT as of \S+\s*$/, " (published fact)"],
];

/** Reasons from the backend can carry a config path in brackets and code names. Both are rewritten for people. */
export function plainReason(text: string | null | undefined): string {
  if (!text) return "";
  let t = text.replace(/\s*\[[a-z0-9_.]+(?: is [0-9.]+)?\]/g, "");
  for (const [rx, to] of REASONS) t = t.replace(rx, to);
  for (const [rx, to] of BASIS) t = t.replace(rx, to);
  return t
    .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})/g, (m) => timeET(m))
    .replace(/(\d+\.\d{2})\d+%/g, "$1%")
    .replace(/\. ([a-z])/g, (_m, c: string) => `. ${c.toUpperCase()}`)
    .replace(/\b[a-z]+_[a-z0-9_]+\b/g, (m) => SIGNALS[m] ?? LIMITS[m] ?? VENDORS[m] ?? LICENSES[m] ?? FAMILIES[m] ?? humanize(m).toLowerCase())
    .trim()
    .replace(/^[a-z]/, (c) => c.toUpperCase());
}
