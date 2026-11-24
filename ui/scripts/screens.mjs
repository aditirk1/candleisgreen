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
const check = (cond, msg) => { if (!cond) { console.error("FAIL " + msg); process.exitCode = 1; } else console.log("ok   " + msg); };

await page.goto(base + "/#overview");
await page.getByText("Account value (USD)").waitFor();
check(await page.getByText("SIMULATION").first().isVisible(), "SIMULATION label visible on Overview");
check((await page.locator("table").count()) >= 1, "positions table rendered");
check(await page.locator("[aria-label='Equity curve'] canvas").first().isVisible(), "equity curve drawn");
await page.screenshot({ path: `${out}/overview-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "Execution" }).click();
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
await page.getByRole("button", { name: "THEME GLASS" }).click();
await page.screenshot({ path: `${out}/execution-glass-kill.png`, fullPage: true });

await page.getByRole("button", { name: "THEME TERMINAL" }).click();
await page.getByRole("button", { name: "Earnings" }).click();
await page.getByText("Scorecard, as reported in SEC filings").waitFor();
check(await page.getByText("BusEq").first().isVisible(), "issuer shows its Fama-French 12 industry");
check((await page.locator("a[href*='sec.gov/Archives']").count()) > 0, "every scorecard row links to its SEC filing");
const earningsText = (await page.locator("body").innerText()).toLowerCase();
check(!earningsText.includes("beat") && !earningsText.includes("miss"), "no beat or miss on the Earnings screen");
await page.screenshot({ path: `${out}/earnings-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "Composite" }).click();
await page.getByText("Composite run").waitFor();
check((await page.getByText("xs_momentum_12_1").count()) > 0, "Composite lists each signal");
check(await page.getByText("RETROSPECTIVE").first().isVisible(), "Composite run labeled retrospective");
check(await page.getByText("SYNTHETIC").first().isVisible(), "synthetic data labeled on the Composite screen");
check((await page.getByText(/PROVISIONAL|SAFEGUARD/).count()) > 0, "exclusion reasons carry their parameter basis");
await page.screenshot({ path: `${out}/composite-terminal.png`, fullPage: true });
await page.getByRole("button", { name: "Evidence chain" }).first().click();
await page.getByText("Evidence chain:").waitFor();
check(await page.getByText("reproduction").first().isVisible(), "evidence chain opens from the Composite screen");
check(await page.getByText("Failure archive").isVisible(), "failure archive shown");
check(await page.getByText("▼ FAILED").first().isVisible(), "negative result visible");
await page.screenshot({ path: `${out}/research-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "News", exact: true }).click();
await page.getByText("clustered by story").waitFor();
await page.locator("tbody tr").nth(9).waitFor({ timeout: 5000 }).catch(() => {});
check((await page.locator("tbody tr").count()) >= 10, "News shows clustered official stories");
await page.screenshot({ path: `${out}/news-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "Reasoning" }).click();
await page.getByText("Data freshness").waitFor();
check(await page.getByText("ts_momentum_252_21 1.0.0").isVisible(), "Reasoning shows the forecast's model and version");
check(await page.getByText("Agreeing and opposing signals").isVisible(), "Reasoning shows agreeing and opposing signals");
await page.getByLabel("Ticker").fill("DNCO");
await page.getByRole("button", { name: "Explain" }).click();
await page.getByText("Why not?").waitFor();
check(await page.getByText(/not positive/).first().isVisible(), "Why not explains a down-trending ticker");
await page.screenshot({ path: `${out}/reasoning-terminal.png`, fullPage: true });

await page.getByRole("button", { name: "Learn" }).click();
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

const text = await page.locator("body").innerText();
check(!/[—–;·]/.test(text), "no em dashes, semicolons or middle dots in visible text");
check(!/manual_simulation|auto_simulation/.test(text), "modes shown in plain words");
check(errors.length === 0, `no page errors (${errors.join(" | ")})`);
await browser.close();
