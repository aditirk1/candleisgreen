# DESIGN_SYSTEM.md

Source: `SPEC.md` v3.2, section "Interface and design system". Built in `ui/src/tokens.css` and `ui/src/app.css`.

## Themes

Three themes over one layout: Light, Dark (Glass) and Terminal, chosen from the Theme menu in the top bar or in Settings. The first visit follows the system's light or dark preference. Components read CSS variables only, so a theme switch changes tokens and nothing else. The commands `THEME TERMINAL` and `THEME GLASS` still work.

| Token | Terminal | Dark (Glass) | Light |
| --- | --- | --- | --- |
| `--bg` | #0B0D10 | gradient #0E1420 to #16213A | #F3F5F9 |
| `--panel` | #12151A with a 1 px #232830 border | white at 6% with a 16 px blur and a white border at 12%. Tables sit on `--panel-solid` at 90% | #FFFFFF with a 1 px #E3E7EE border |
| `--text`, `--muted` | #D7DCE2, #8A93A0 | #E8EDF5, #9AA6B8 | #111827, #4B5563 |
| `--accent` | #FFB000 | #5B8CFF | #2F5BD3 |
| `--gain`, `--loss` | #3FB950, #F85149 | #34C78A, #FF6B6B | #0F7A55, #C2303B |
| Numbers | IBM Plex Mono or JetBrains Mono, tabular | Inter, tabular | Inter, tabular |
| Rows, corners | 28 px, 2 px | 40 px, 12 px | 40 px, 12 px |

The light accent, gain and loss are darker than the Glass values because the spec's 4.5:1 contrast rule fails for #5B8CFF and #34C78A on white. When the system asks for reduced transparency, Glass panels turn solid. Motion is limited to fades under 150 ms.

## Layout

- A left sidebar groups the screens: Today (Overview, News), Trade (Opportunities, Execution, Reasoning), Markets (Markets, Earnings, Global), Research (Research, Composite, Backtests, Experts), Learn, System (Audit and Rules, Settings). On a narrow screen it folds behind a Menu button.
- Details are one click away, never on screen by default. Opportunities rows open their evidence underneath. News cards open into what happened, why it may matter and what prices did. Learn and Research split into tabs.
- Any ticker opens the stock panel: what the company is, its price and chart, what the system thinks in plain words, any planned trade, and news that names it. Typing a ticker in the top bar opens it too.
- News shows stories that name a listed company or concern interest rates first. Everything else folds under Other official news.
- The first-run tour shows each step only on its own screen.

## Rules for every string

No em dashes, semicolons, middle dots, tildes as separators, filler, metaphors, slogans or exclamation marks. Units go in column headers. Times are 24-hour with zone (14:32 ET) and dates ISO. Gains and losses always carry a sign or arrow, never color alone. A missing value reads NOT AVAILABLE with its reason. `ui/scripts/screens.mjs` checks the visible text of every screen for banned punctuation on every run.

## Status strip

Always visible in the top bar: PAPER or SIMULATION, mode in plain words, time, one status chip (Systems OK, or the parts that are not OK, with every part listed on hover), the search and command box, Guide mode, the theme menu and the kill switch.

Verbatim source text, such as headlines and filing summaries, is shown as published and marked `data-source-text`. The punctuation check covers everything the app writes and skips only that marked text.

## Screens built

All fifteen spec screens, the command bar, Guide mode, the first-run tour and the stock panel.
