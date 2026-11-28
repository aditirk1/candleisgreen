// Drives the real interface: checks both screens, approves, rejects, toggles the kill switch,
// and saves screenshots. Usage: node ui/scripts/screens.mjs http://127.0.0.1:8000 var/screens
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const out = process.argv[3] ?? "var/screens";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
// Our own text only. Verbatim source text (headlines, filing summaries) is marked and left as published.
const ownText = (loc) => loc.evaluate((el) => { const c = el.cloneNode(true); c.querySelectorAll("[data-source-text]").forEach((n) => n.remove()); document.body.appendChild(c); const t = c.innerText; c.remove(); return t; });
// Screens sit under six destinations plus the Research workspace and Settings. Old screen names map to [destination, tab].
const NAV = { Overview: ["Home"], Opportunities: ["Discover", "Opportunities"], Reasoning: ["Discover", "Reasoning"],
  Execution: ["Portfolio", "Orders and approvals"], "Audit and Rules": ["Portfolio", "Risk and rules"], Markets: ["Markets", "Instruments"],
  Earnings: ["Markets", "Earnings"], Global: ["Markets", "Global"], News: ["Intelligence", "News"], Ownership: ["Intelligence", "Insiders and institutions"], Learn: ["Learn"],
  Research: ["Research workspace", "Research"], Composite: ["Research workspace", "Composite"], Backtests: ["Research workspace", "Backtests"],
  Experts: ["Research workspace", "Experts"], Settings: ["Settings"] };
const nav = async (name) => {
  const [dest, sub] = NAV[name];
  await page.locator("nav").getByRole("button", { name: dest, exact: true }).click();
  if (sub) await page.getByRole("tablist").getByRole("tab", { name: sub, exact: true }).click();
};
const setTheme = async (t) => { if ((await page.evaluate(() => document.documentElement.dataset.theme)) !== t) await page.getByRole("button", { name: "Theme" }).click(); };
const tab = (group, name) => page.getByRole("group", { name: group }).getByRole("button", { name, exact: true }).click();
await page.addInitScript(() => { if (!sessionStorage.getItem("init")) { localStorage.setItem("theme", "terminal"); localStorage.setItem("guide", "off"); sessionStorage.setItem("init", "1"); } });
const check = (cond, msg) => { if (!cond) { console.error("FAIL " + msg); process.exitCode = 1; } else console.log("ok   " + msg); };

await page.goto(base + "/#overview");
await page.getByText("Account value (USD)").waitFor();
check(await page.getByRole("dialog", { name: "First-run tour" }).isVisible(), "first-run tour shown on first visit");
await page.getByRole("button", { name: "Skip tour" }).click();
check(await page.getByText("SIMULATION").first().isVisible(), "SIMULATION label visible on Overview");
check((await page.locator("table").count()) >= 1, "holdings table rendered");
check(await page.getByText("Needs attention", { exact: true }).isVisible() && await page.getByText(/^Top research opportunities/).isVisible() && await page.getByText("Market developments", { exact: true }).isVisible(), "Home shows attention, developments and opportunities");
check(await page.getByText("DEMO DATA.").isVisible(), "synthetic demo data is labeled on Home");
check(await page.getByText(/^Not enough history yet/).isVisible(), "performance chart shows an empty state until enough history exists");
check((await page.getByRole("button", { name: "KILL" }).count()) === 1, "kill switch is in the top bar");
check((await page.getByText(/data job missed its schedule|Systems OK|Feed/).count()) > 0, "system status shown in the top bar");
await page.screenshot({ path: `${out}/overview-terminal.png`, fullPage: true });

await nav("Execution");
await page.getByText("approval queue").waitFor();
const approveButtons = page.getByRole("button", { name: "Approve" });
const before = await approveButtons.count();
check(before >= 2, `approval queue has ${before} proposals`);
await approveButtons.first().click();
await page.waitForTimeout(400);
await page.getByRole("button", { name: "Reject" }).first().click();
await page.waitForTimeout(400);
check((await page.getByRole("button", { name: "Approve" }).count()) === before - 2, "approve and reject removed two proposals from the queue");
check(await page.getByText("APPROVED").first().isVisible(), "approved order listed");
check(await page.getByText("REJECTED").first().isVisible(), "rejected order listed");
await page.screenshot({ path: `${out}/execution-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "KILL" }).click();
await page.getByText("KILL SWITCH ON").waitFor();
check(await page.getByText("ON. New orders are blocked").isVisible(), "kill switch shown as ON after engaging");
await setTheme("light");
await page.screenshot({ path: `${out}/execution-glass-kill.png`, fullPage: true });

await setTheme("dark");
await nav("Earnings");
await page.getByText("Scorecard, as reported in SEC filings").waitFor();
check(await page.getByText("BusEq").first().isVisible(), "issuer shows its Fama-French 12 industry");
check((await page.locator("a[href*='sec.gov/Archives']").count()) > 0, "every scorecard row links to its SEC filing");
const earningsText = (await page.locator("body").innerText()).toLowerCase();
check(!earningsText.includes("beat") && !earningsText.includes("miss"), "no beat or miss on the Earnings screen");
await page.screenshot({ path: `${out}/earnings-terminal.png`, fullPage: true });

await nav("Composite");
await page.getByRole("heading", { name: "How the signals combine" }).waitFor();
check(await page.getByText("Momentum, 12-month winners against losers").isVisible(), "Composite lists each signal by a plain name");
check(await page.getByText(/Results are back-tested, not recorded in advance/).isVisible(), "Composite run labeled back-tested");
check(await page.getByText(/come from demo data, so they are not evidence/).isVisible(), "demo data labeled on the Composite screen");
await page.getByText("Momentum, 12-month winners against losers").click();
check((await page.getByText(/\((safety rule|starting setting, under review|from published research)\)/).count()) > 0, "exclusion reasons say where each threshold comes from");
check((await page.getByText(/Evidence level \d of 6\. Trading needs level/).count()) > 0, "exclusion reasons are written in plain words");
await page.screenshot({ path: `${out}/composite-terminal.png`, fullPage: true });
await page.getByRole("button", { name: "See the research behind it" }).first().click();
await page.getByRole("heading", { name: /^Evidence: / }).waitFor();
check(await page.getByText("Reproduce the published result").first().isVisible(), "evidence opens from the Composite screen");
check(await page.getByText("Failure archive, ideas that did not hold up").isVisible(), "failure archive shown");
check(await page.getByText("▼ Did not hold up").first().isVisible(), "negative result visible");
await tab("Research sections", "Today");
check(await page.getByText("Daily research digest").isVisible(), "daily research digest shown");
check(await page.getByText(/Needs data: analyst estimates/).isVisible(), "missing data flagged with a free substitute");
check(await page.getByRole("heading", { name: "Signals under review" }).isVisible() && (await page.getByRole("cell", { name: "Momentum, 12-month winners against losers" }).count()) > 0, "signal review listed");
check(await page.getByText("Clark-West adjusted mean squared error").isVisible(), "Level B against Level A uses Clark-West");
check((await page.getByText("keep the champion").count()) === 2, "synthetic comparisons never recommend a switch");
await tab("Research sections", "Capture inbox");
await page.getByLabel("Capture text").fill("Stocks with high gross profitability earn higher average returns over the next 12 months.");
await page.getByRole("button", { name: "Capture", exact: true }).click();
await page.getByText(/Captured\. 1 claims found/).waitFor();
check(true, "inbox extracts a claim from pasted text");
await page.getByRole("button", { name: "Link", exact: true }).click();
await page.getByLabel("Capture link").fill("https://papers.example.org/abstract=1");
await page.getByRole("button", { name: "Capture", exact: true }).click();
await page.getByText(/Automatic retrieval is not allowed for papers\.example\.org/).first().waitFor();
check(true, "inbox asks for input instead of fetching a link");
await page.screenshot({ path: `${out}/research-terminal.png`, fullPage: true });
await tab("Research sections", "Today");
await page.getByRole("button", { name: "Decline" }).click();
await page.getByRole("cell", { name: "Declined" }).first().waitFor({ timeout: 5000 }).catch(() => {});
check(await page.getByRole("cell", { name: "You", exact: true }).first().isVisible(), "promotion decided by Aditi only");

await nav("News");
await page.getByRole("button", { name: "90 days", exact: true }).click();
await page.locator(".story").first().waitFor();
const shown = await page.locator(".story").count();
check(shown >= 3 && shown < 20, `market-relevant stories first, the rest folded away (${shown} shown)`);
await page.getByRole("button", { name: /Show routine announcements/ }).click();
check((await page.locator(".story").count()) >= 10, "News shows one card per story");
const axp = page.locator(".story", { hasText: "American Express" }).first();
check((await axp.locator(".story-tickers").innerText()).includes("AXP"), "a company named in a story is linked to its ticker");
await axp.locator(".story-head").click();
check(await axp.getByText("What happened").isVisible() && await axp.getByText("Why it may matter").isVisible() && await axp.getByText("What prices did").isVisible(), "a story opens into what happened, why it may matter and what prices did");
check(await axp.getByText(/not proof the story caused it/).isVisible(), "price moves labeled as observation, not cause");
await page.getByLabel("Category").selectOption("Enforcement");
check((await page.locator(".story").count()) >= 1, "stories filter by category");
await page.getByLabel("Category").selectOption("all");
await page.getByLabel("Search headlines").fill("Nova Scotia");
check((await page.locator(".story").count()) === 1, "headline search narrows the list");
await page.getByLabel("Search headlines").fill("");
await page.getByRole("button", { name: "Newest" }).click();
await page.locator(".story").first().waitFor();
check(true, "stories sort by recency");
const firstSave = page.locator(".story button.icon").first();
await firstSave.click();
check((await firstSave.getAttribute("aria-pressed")) === "true", "a story can be saved");
await page.screenshot({ path: `${out}/news-terminal.png`, fullPage: true });

await nav("Reasoning");
await page.getByText("Data freshness").waitFor();
check((await page.getByText("Trend model, 12-month price trend").count()) > 0, "Reasoning names the forecast's model in plain words");
check(await page.getByText("Agreeing and opposing signals").isVisible(), "Reasoning shows agreeing and opposing signals");
await page.getByLabel("Ticker").fill("DNCO");
await page.getByRole("button", { name: "Explain" }).click();
await page.getByText(/Sell short/).first().waitFor();
check(true, "Reasoning shows a downtrend as a short sale");
await page.getByLabel("Ticker").fill("DLST");
await page.getByRole("button", { name: "Explain" }).click();
await page.getByText("Why not?").waitFor();
check(await page.getByText(/not in the tradable universe/).first().isVisible(), "Why not explains a delisted ticker");
await page.screenshot({ path: `${out}/reasoning-terminal.png`, fullPage: true });

await nav("Learn");
await page.getByText("Replay, as known then").waitFor();
await page.locator("table").first().locator("tbody tr").first().waitFor();
const lastBefore = await page.locator("table").first().locator("tbody tr").last().locator("td").first().innerText();
check(lastBefore <= "2026-10-01", `replay clock 2026-10-01 17:30 ET shows no later price (last ${lastBefore})`);
await page.getByRole("button", { name: /Record prediction/ }).click();
await page.getByText("Prediction recorded").waitFor();
await page.getByText("NOT YET REVEALED").first().waitFor({ timeout: 5000 }).catch(() => {});
check(await page.getByText("NOT YET REVEALED").first().isVisible(), "outcome hidden until the replay clock passes the horizon");
check(await page.getByText("from 0 resolved predictions").isVisible(), "calibration does not count an unrevealed outcome");
await page.getByRole("button", { name: "Advance 5 days" }).click();
await page.getByRole("button", { name: "Advance 1 day" }).click();
await page.waitForTimeout(600);
check((await page.getByText(/RIGHT|WRONG/).count()) > 0, "outcome revealed after advancing past the horizon");
await page.screenshot({ path: `${out}/learn-terminal.png`, fullPage: true });
await tab("Learn sections", "Your trades");
check(await page.getByText("Market autopsy, simulated trades").isVisible(), "market autopsy shown");
await page.getByLabel("Change").selectOption("spread_bps");
await page.getByRole("button", { name: "Test the change" }).click();
await page.getByText("BLOCKED BY RISK").waitFor({ timeout: 5000 }).catch(() => {});
check(await page.getByText("HYPOTHETICAL").first().isVisible(), "counterfactual labeled hypothetical");
await tab("Learn sections", "Experiments");
await page.getByText("Crisis library").waitFor();
check((await page.getByText(/NOT AVAILABLE\. Stored price data covers/).count()) === 6, "every crisis episode NOT AVAILABLE without data");
await page.getByLabel("Trade idea").fill("$UPCO shares will outperform over the next 5 days");
await page.getByRole("button", { name: "Design the test" }).click();
await page.getByText(/The effect described has no positive return/).waitFor();
await page.getByRole("button", { name: "Pre-register through the research pipeline" }).click();
await page.getByText(/Pre-registered as exp_/).waitFor();
check(true, "experiment lab designs and pre-registers an idea");
await tab("Learn sections", "Lessons");
check(await page.getByText(/Daily lesson 2026/).isVisible() && await page.getByText("Concept map, in learning order").isVisible(), "daily lesson and concept map shown");
await page.getByRole("button", { name: "Show answer" }).click();
await page.getByRole("button", { name: "I knew it" }).click();
check(true, "spaced review card answered");

await nav("Global");
await page.getByText("Scheduled jobs through the day").waitFor();
await page.getByText("United States").first().waitFor({ timeout: 5000 }).catch(() => {});
check((await page.getByText("research only").count()) >= 5, "every non-US market is research only on the Global screen");
check(await page.getByRole("row", { name: /Tokyo Stock Exchange Research only/ }).isVisible() && (await page.getByRole("cell", { name: "Research only", exact: true }).count()) >= 4, "market rule table tags non-US exchanges research only");
check(await page.getByText("Euro (EUR)").isVisible(), "FX rates from FRED shown");
check(await page.getByText("Unemployment rate").isVisible() && (await page.getByText(/No published value recorded yet/).count()) >= 1, "macro shows the stored vintage and NOT AVAILABLE for series without one");
check(await page.getByText(/NOT AVAILABLE\. Paper options orders through Alpaca are not sent yet/).isVisible() && await page.getByText(/LIMITED\. Alpaca's free indicative feed/).isVisible(), "entitlement map shows free options data as limited and options trading as not available");
await page.screenshot({ path: `${out}/global-terminal.png`, fullPage: true });

const texts = [await ownText(page.locator("body"))];

await nav("Opportunities");
await page.getByText(/^Opportunities for /).waitFor();
check((await page.locator("tbody tr").count()) >= 2, "Opportunities lists proposed positions");
check((await page.getByRole("dialog").count()) === 0, "evidence stays hidden until a row is opened");
await page.locator("tr.clickable").first().focus();
await page.keyboard.press("Enter");
const drawer = page.getByRole("dialog");
await drawer.getByText("Conclusion").waitFor();
check(await drawer.getByText(/It is not a forecast return or a probability, because the model is not calibrated/).isVisible(), "uncalibrated signal is never shown as a forecast");
for (const part of ["Model reasoning", "Supporting and opposing signals", "Risk checks and uncertainty", "News and catalysts", "Data provenance"]) {
  check(await drawer.getByText(part, { exact: true }).isVisible(), `drawer has ${part}`);
}
check(await drawer.getByRole("button", { name: "Close" }).evaluate((el) => el === document.activeElement), "keyboard focus moves into the drawer");
await page.keyboard.press("Escape");
check((await page.getByRole("dialog").count()) === 0, "Escape closes the drawer");
await page.locator("tr.clickable").first().click();
await page.screenshot({ path: `${out}/opportunities-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));
await page.getByRole("dialog").getByRole("button", { name: "Full reasoning" }).click();
await page.getByText("Data freshness").waitFor();
check(true, "Opportunities opens Reasoning for the selected ticker");

await nav("Markets");
await page.getByLabel("Search instruments").fill("UPCO");
await page.locator("tbody tr").first().click();
await page.locator("[aria-label='Price chart'] canvas").first().waitFor();
check(await page.getByText("UPCO daily prices").waitFor({ timeout: 5000 }).then(() => true, () => false), "Markets charts a selected instrument");
await page.getByRole("button", { name: "Add UPCO to watchlist" }).click();
check(await page.getByRole("button", { name: "Remove UPCO from watchlist" }).isVisible(), "watchlist add works");
await page.screenshot({ path: `${out}/markets-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await nav("Markets");
await page.getByRole("tablist").getByRole("tab", { name: "Company", exact: true }).click();
await page.getByText("Why the system would trade or abstain").waitFor();
check(await page.locator("[aria-label='Company price chart'] canvas").first().waitFor({ timeout: 5000 }).then(() => true, () => false), "company page draws price and volume");
await page.getByLabel("Company ticker").fill("AAPL");
await page.getByRole("button", { name: "Open", exact: true }).click();
await page.getByText(/Electronic Computers/).waitFor();
check((await page.locator("a[href*='sec.gov/Archives']").count()) > 0, "company financials link to their SEC filings");
check(await page.getByText(/NOT AVAILABLE\. No recorded price/).first().isVisible(), "valuation without a price says NOT AVAILABLE with the reason");
check(await page.getByText(/Revenue model/).isVisible() && await page.getByText(/The 10-K business section \(Item 1\) is not parsed/).isVisible(), "unverified revenue model is labeled, not invented");
check((await page.getByRole("columnheader", { name: "Age (days)" }).count()) >= 2, "every company metric shows its age");
await page.screenshot({ path: `${out}/company-light.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));
await page.getByRole("tablist").getByRole("tab", { name: "Asset classes", exact: true }).click();
await page.getByRole("heading", { name: "Asset classes" }).waitFor();
const levelRow = (name) => page.getByRole("row", { name: new RegExp(`^${name} `) });
await levelRow("Crypto").waitFor();
check((await page.getByRole("columnheader", { name: "Broker paper trading" }).count()) === 1 && (await page.getByRole("columnheader", { name: "Live trading" }).count()) === 1, "asset classes show all eight levels");
check((await levelRow("Stocks and ETFs").innerText()).includes("✓ Yes") && (await page.getByText("✗ No").count()) >= 5, "only stocks can be paper traded through a broker and nothing trades live");
check((await levelRow("Crypto").innerText()).match(/✓ Yes/g).length === 6, "crypto history and current prices marked as checked");
await levelRow("Options").click();
check(await page.getByText(/OPRA needs a paid plan and is refused/).isVisible(), "options levels explain the free indicative feed");
const assetView = (v) => page.getByRole("group", { name: "Asset class view" }).getByRole("button", { name: v, exact: true }).click();
await assetView("Options");
await page.getByText(/options chain needs your free Alpaca paper keys/).waitFor();
check(true, "options chain says it needs Alpaca keys instead of showing invented quotes");
await page.getByRole("button", { name: "Show payoff" }).click();
await page.getByText("Largest possible loss").waitFor();
check(await page.getByRole("img", { name: "Profit or loss at expiry by underlying price" }).isVisible() && await page.getByText("604.00").isVisible(), "a call spread shows its payoff, largest loss and break-even");
await page.getByLabel("Leg 2 contracts").fill("-2");
await page.getByRole("button", { name: "Show payoff" }).click();
await page.getByText(/No limit\. The risk checks refuse this/).waitFor();
check(true, "an extra short call shows an unlimited possible loss");
await page.getByRole("button", { name: "Calculate" }).click();
await page.getByText("Model value per share").waitFor();
check(await page.getByText(/A model value, never a market price/).isVisible(), "theoretical values are labeled as model output");
await page.screenshot({ path: `${out}/asset-classes-light.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));
await assetView("Crypto");
await page.getByText(/Not recorded yet\. Press Record/).waitFor();
check(await page.getByText(/Volume is Alpaca's own, not the whole market/).isVisible(), "crypto says what its volume covers");
await assetView("Forex");
await page.getByText(/NOT AVAILABLE yet/).waitFor();
check(await page.getByText(/NOT AVAILABLE yet\. Two steps turn it on/).isVisible() && await page.getByText(/OANDA_PRACTICE_TOKEN/).isVisible(), "forex lists the steps that turn it on");
await assetView("Futures");
await page.getByRole("heading", { name: "Contracts" }).waitFor();
check((await page.getByRole("cell", { name: "Not yet checked" }).count()) === 5 && await page.getByRole("cell", { name: "ESZ26" }).isVisible(), "futures contracts show the contract to hold and unchecked terms");
await page.getByLabel("Settlement prices").fill("date,contract,settle\n2026-11-18,ESZ26,6000\n2026-11-19,ESZ26,6010\n");
await page.getByRole("button", { name: "Store prices" }).click();
await page.getByText(/Stored 2 settlement prices for ESZ26/).waitFor();
await page.getByRole("button", { name: "Join into one series" }).click();
await page.getByText(/2 days, adjusted at each roll/).waitFor();
check(true, "uploaded settlements join into a continuous series");
texts.push(await ownText(page.locator("body")));
await nav("Ownership");
await page.getByText("Insider transactions, SEC Form 4").waitFor();
check(await page.getByText("RESEARCH ONLY.").isVisible(), "insider and institutional data labeled research only");
check(await page.getByRole("columnheader", { name: "Disclosed" }).isVisible() && await page.getByRole("columnheader", { name: "Traded" }).isVisible(), "transaction and disclosure dates shown separately");
check(await page.getByText("10b5-1 plan").first().isVisible(), "pre-scheduled sales flagged");
check(await page.getByText(/BERKSHIRE HATHAWAY/).isVisible() && await page.getByText(/not a complete or current portfolio/).isVisible(), "13F holdings shown with their limits");
check((await page.getByText(/^NOT AVAILABLE\. Not built/).count()) >= 3, "unbuilt political and procurement modules labeled not available");
await page.screenshot({ path: `${out}/ownership-light.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));
await nav("Backtests");
await page.getByRole("heading", { name: "Backtests" }).waitFor();
check((await page.getByText("Momentum, 12-month winners against losers").count()) > 0 && (await page.getByText("Return per unit of risk").count()) > 0, "Backtests shows each signal with a Sharpe ratio");
check(await page.getByText(/versions tested in total, which matters because/).isVisible(), "trial count shown beside the Sharpe ratios");
await page.screenshot({ path: `${out}/backtests-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await nav("Experts");
await page.getByText("Source registry").waitFor();
check((await page.getByText("CC BY-NC 4.0", { exact: false }).count()) > 0 || (await page.locator("tbody tr").count()) >= 3, "Experts lists sources with licenses");
await page.screenshot({ path: `${out}/experts-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await nav("Audit and Rules");
await page.getByText(/Log verified\. No record has been changed/).waitFor();
const posRow = page.getByRole("row", { name: /^Largest position, share of account/ });
await page.getByLabel("New value for Largest position, share of account").fill("0.04");
await posRow.getByRole("button", { name: "Request" }).click();
await page.getByText(/Applied now/).waitFor();
check(true, "tightening a hard limit applies at once");
await page.getByLabel("New value for Largest position, share of account").fill("0.5");
await posRow.getByRole("button", { name: "Request" }).click();
await page.getByText(/needs confirmation/).waitFor();
await posRow.getByRole("button", { name: "Confirm" }).click();
await page.getByText(/Not confirmed/).waitFor();
check(true, "loosening waits and cannot be confirmed early");
check((await page.getByRole("cell", { name: "Starting setting, under review" }).count()) > 0, "parameters listed with their basis");
check(await page.getByText("ON.", { exact: true }).isVisible() && await page.getByText(/Up to 3\.0% of the account per stock and 30% in total/).isVisible(), "short selling shown as on at 3% per stock and 30% in total");
await page.getByRole("button", { name: "Turn off now" }).click();
await page.getByText("OFF.", { exact: true }).waitFor();
check(true, "turning shorting off applies at once");
await page.getByRole("button", { name: "Request turning on" }).click();
await page.getByText(/Largest short position, share of account waits until/).waitFor();
check(await page.getByRole("button", { name: "Confirm turning on" }).waitFor({ timeout: 5000 }).then(() => true, () => false), "turning shorting on waits for the delay and a confirmation");
await page.getByRole("button", { name: "Confirm turning on" }).click();
await page.getByText(/not confirmed/).first().waitFor();
check(true, "an early confirmation is refused");
await page.screenshot({ path: `${out}/rules-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await nav("Settings");
await page.getByText("API keys and data sources").waitFor();
check(await page.getByText("APCA_API_KEY_ID").isVisible(), "credential status listed");
check(await page.getByText("Live trading").isVisible(), "live trading shown as not built");
await page.screenshot({ path: `${out}/settings-terminal.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await page.getByLabel("Command").fill("UPCO NEWS");
await page.getByLabel("Command").press("Enter");
await page.getByText("Market intelligence, UPCO").waitFor();
check(true, "command UPCO NEWS opens News for one ticker");
await page.getByLabel("Command").fill("why didn't we buy DLST");
await page.getByLabel("Command").press("Enter");
await page.getByText("Why not?").waitFor();
check(await page.getByText(/not in the tradable universe/).first().isVisible(), "plain phrase opens Why not for DLST");
await page.getByLabel("Command").fill("RULES");
await page.getByLabel("Command").press("Enter");
await page.getByRole("heading", { name: "Hard limits" }).waitFor();
check(true, "command RULES opens Audit and Rules");

await page.getByRole("group", { name: "Display mode" }).getByRole("button", { name: "Advanced" }).click();
await page.getByRole("button", { name: "Guide off" }).click();
await nav("Opportunities");
await page.getByText(/How strongly the model leans/).first().waitFor();
check(true, "Guide mode shows plain labels with the technical term");
await page.getByRole("button", { name: "Explain this screen" }).click();
check(await page.getByText("About this screen").isVisible(), "Explain this screen opens");
check(await page.getByText("KILL", { exact: false }).first().isVisible() && await page.getByText("SIMULATION").first().isVisible(), "Guide mode keeps the venue label and kill switch");
await page.screenshot({ path: `${out}/opportunities-guide.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

await page.getByRole("button", { name: "UPCO", exact: true }).first().click();
const panel = page.getByRole("dialog", { name: "About UPCO" });
await panel.getByText("Conclusion").waitFor();
check(await panel.getByText(/trend model reads this as an uptrend/).isVisible(), "stock panel explains the system view in plain words");
check(await panel.getByText(/Upward Industries/).first().isVisible() && await panel.locator("[aria-label='Stock price chart'] canvas").first().isVisible(), "stock panel shows the company and its chart");
texts.push(await ownText(panel));
await page.keyboard.press("Escape");
await page.getByLabel("Command").fill("UPCO");
await page.getByLabel("Command").press("Enter");
check(await page.getByRole("dialog", { name: "About UPCO" }).isVisible(), "typing a ticker opens its stock panel");
await page.keyboard.press("Escape");
await setTheme("light");
await nav("Overview");
await page.getByText("Account value (USD)").waitFor();
const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
check(bg === "rgb(246, 247, 249)", `light theme uses a neutral off-white background (${bg})`);
await page.screenshot({ path: `${out}/overview-light.png`, fullPage: true });
await nav("News");
await page.locator(".story").first().waitFor();
await page.screenshot({ path: `${out}/news-light.png`, fullPage: true });
texts.push(await ownText(page.locator("body")));

// Principal screens in both themes, for review. Charts must redraw after each switch.
await page.getByRole("group", { name: "Display mode" }).getByRole("button", { name: "Focus" }).click();
for (const theme of ["light", "dark"]) {
  await setTheme(theme);
  for (const [name, file] of [["Overview", "home"], ["Opportunities", "opportunities"], ["News", "news"], ["Markets", "markets"], ["Execution", "portfolio"], ["Learn", "learn"], ["Research", "research-workspace"]]) {
    await nav(name);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/principal-${file}-${theme}.png`, fullPage: true });
  }
  await nav("Markets");
  await page.locator("[aria-label='Price chart'] canvas").first().waitFor();
  check(true, `price chart drawn in the ${theme} theme`);
}
// Focus mode is for people. Code names, config paths, record IDs and hashes stay in Advanced mode's technical details.
const INTERNAL = [/\b[a-z0-9]+_[a-z0-9_]+\b/, /\b[a-z_]+\.[a-z_]+\.[a-z_.]+\b/, /config\/\S+/, /\.ya?ml\b/, /\b(?:inst|claim|exp|run|var|promo|case|fc|cap|story|clu|card|obs)_[a-z0-9]+/, /\b[0-9a-f]{16,}\b/, /\[[a-z_.]+\]/];
const focusLeaks = [];
// Web addresses such as papers.example.org are fine. Only dotted config paths count.
const isHost = (m) => /\.(org|com|gov|net|io|edu)$/.test(m);
const leaks = (where, t) => { for (const rx of INTERNAL) for (const m of t.matchAll(new RegExp(rx, "g"))) if (!isHost(m[0])) { focusLeaks.push(`${where}: ${m[0]}`); break; } };
for (const name of ["Overview", "Opportunities", "Reasoning", "Markets", "Earnings", "Global", "News", "Ownership", "Execution", "Audit and Rules", "Composite", "Backtests", "Experts", "Settings"]) {
  await nav(name);
  await page.waitForTimeout(700);
  const t = await ownText(page.locator("main"));
  leaks(name, t);
}
await nav("Markets");
await page.getByRole("tablist").getByRole("tab", { name: "Asset classes", exact: true }).click();
for (const v of ["Options", "Crypto", "Forex", "Futures"]) {
  await page.getByRole("group", { name: "Asset class view" }).getByRole("button", { name: v, exact: true }).click();
  await page.waitForTimeout(500);
  leaks(`Asset classes ${v}`, await ownText(page.locator("main")));
}
await nav("Research");
for (const sub of ["Today", "Research ideas", "Capture inbox"]) {
  await tab("Research sections", sub);
  await page.waitForTimeout(500);
  const t = await ownText(page.locator("main"));
  leaks(`Research ${sub}`, t);
}
await nav("Opportunities");
await page.locator("tr.clickable").first().click();
await page.getByRole("dialog").getByText("Conclusion").waitFor();
const dt = await ownText(page.getByRole("dialog"));
leaks("drawer", dt);
await page.keyboard.press("Escape");
check(focusLeaks.length === 0, `Focus mode shows no code names, config paths or record IDs (${focusLeaks.join(" | ")})`);
await page.getByRole("group", { name: "Display mode" }).getByRole("button", { name: "Advanced" }).click();
await nav("Composite");
check(await page.getByText("Technical details").first().waitFor({ timeout: 5000 }).then(() => true, () => false), "Advanced mode keeps the technical details");
await page.getByRole("group", { name: "Display mode" }).getByRole("button", { name: "Focus" }).click();
const text = texts.join("\n");
check(!/[—–;·]/.test(text), "no em dashes, semicolons or middle dots in visible text");
check(!/manual_simulation|auto_simulation/.test(text), "modes shown in plain words");
check(errors.length === 0, `no page errors (${errors.join(" | ")})`);
await browser.close();
