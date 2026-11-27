# DESIGN_SYSTEM.md

Source: `SPEC.md` v3.2, section "Interface and design system". Built in `ui/src/tokens.css` and `ui/src/app.css`.

## Themes

Two themes: Light (default when the system prefers light) and Dark (the terminal theme). The choice is saved in the browser. Every color, size and surface comes from tokens in `ui/src/tokens.css`. Charts read the chart tokens and redraw when the theme changes.

| Token group | Light | Dark |
| --- | --- | --- |
| Background, surface, raised surface | #F6F7F9, #FFFFFF, #F1F3F6 | #0B0D10, #12151A, #171B21 |
| Border, strong border, hover | #E2E5EA, #C9CED6, #EEF1F5 | #232830, #343B46, #1A1E25 |
| Text, muted text | #111827, #4B5563 | #D7DCE2, #8A93A0 |
| Accent, focus ring | #1F4FBF | #FFB000 |
| Gain, loss, warning | #0F7A55, #B42330, #8A5A00 | #3FB950, #F85149, #E3B341 |
| Chart line, grid, up, down, volume | #1F4FBF, #ECEFF3, #0F7A55, #B42330, gray at 25% | #FFB000, #1C2028, #3FB950, #F85149, gray at 30% |
| Type scale | 12, 13, 14, 18, 26 px. Inter for text, IBM Plex Mono for numbers | Same sizes. IBM Plex Sans for text |
| Corners, row height | 8 px, 40 px | 4 px, 34 px |

Light text colors keep at least 4.5:1 contrast on white. Neither theme uses gradients, translucency or blur. The earlier Glass theme is retired, and a saved Glass or Terminal choice maps to Dark.

## Information architecture

Six destinations in the sidebar, with contextual tabs inside each:

| Destination | Tabs (screen IDs in brackets) |
| --- | --- |
| Home | Home (`overview`) |
| Discover | Opportunities (`opportunities`), Reasoning (`reasoning`) |
| Markets | Instruments (`markets`), Earnings (`earnings`), Global (`global`) |
| Intelligence | News (`news`) |
| Portfolio | Orders and approvals (`execution`), Risk and rules (`rules`) |
| Learn | Learn (`learn`), with its own Practice, Lessons, Your trades and Experiments tabs |

Below a divider: the Research workspace (Research, Composite, Backtests, Experts) and Settings. Screen IDs, URL hashes and every command bar command are unchanged. Back and forward follow the URL hash.

Focus mode (default) shows conclusions and the columns a decision needs. Advanced mode adds detail columns (volatility, trading volume, tier, tag, sector), the news relevance breakdown, System Health open by default, and the Guide controls. Safety items never depend on the mode: the venue label, the kill switch, failures in the status chip and critical Needs Attention items always show.

## Layout

- Conclusions first, evidence one click away. The opportunity drawer opens with its conclusion, then folds model reasoning, signals, risk checks, news and provenance.
- Any ticker opens the evidence drawer. It is a modal dialog: focus moves in, Tab stays inside, Escape closes, and focus returns to where it was. Rows open it with Enter or Space.
- Home order: demo or live data banner, account summary, performance, Needs Attention beside market developments, top opportunities, watchlist beside positions, System Health folded.
- Charts: candlesticks with volume or a line, with 1M, 3M, 6M, 1Y and All ranges.

## Rules for every string

No em dashes, semicolons, middle dots, tildes as separators, filler, metaphors, slogans or exclamation marks. Units go in column headers. Times are 24-hour with zone (14:32 ET) and dates ISO. Gains and losses always carry a sign or arrow, never color alone. A missing value reads NOT AVAILABLE with its reason. `ui/scripts/screens.mjs` checks the visible text of every screen for banned punctuation on every run.

## Status strip

Always visible in the top bar: the venue label (PAPER or SIMULATION), mode in plain words, time, a status chip that appears only when a part is failing, the search and command box, Focus and Advanced, the theme switch and the kill switch.

Verbatim source text, such as headlines and filing summaries, is shown as published and marked `data-source-text`. The punctuation check covers everything the app writes and skips only that marked text.

## Screens built

All fifteen spec screens, the command bar, Guide mode, the first-run tour and the stock panel.
