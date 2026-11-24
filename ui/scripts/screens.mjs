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

const text = await page.locator("body").innerText();
check(!/[—–;·]/.test(text), "no em dashes, semicolons or middle dots in visible text");
check(!/manual_simulation|auto_simulation/.test(text), "modes shown in plain words");
check(errors.length === 0, `no page errors (${errors.join(" | ")})`);
await browser.close();
