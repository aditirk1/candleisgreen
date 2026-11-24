# DESIGN_SYSTEM.md

Source: `SPEC.md` v3.2, section "Interface and design system". Built in `ui/src/tokens.css` and `ui/src/app.css`.

## Themes

Two themes over one layout. Components read CSS variables only, so a theme switch changes tokens and nothing else. The button in the status strip reads THEME GLASS or THEME TERMINAL.

| Token | Terminal | Glass |
| --- | --- | --- |
| `--bg` | #0B0D10 | gradient #0E1420 to #16213A |
| `--panel` | #12151A with a 1 px #232830 border | white at 6% with a 16 px blur and a white border at 12%. Tables sit on `--panel-solid` at 90% |
| `--text`, `--muted` | #D7DCE2, #8A93A0 | #E8EDF5, #9AA6B8 |
| `--accent` | #FFB000 | #5B8CFF |
| `--gain`, `--loss` | #3FB950, #F85149 | #34C78A, #FF6B6B |
| Numbers | IBM Plex Mono or JetBrains Mono, tabular | Inter, tabular |
| Rows, corners | 28 px, 2 px | 40 px, 12 px |

When the system asks for reduced transparency, Glass panels turn solid. Motion is limited to fades under 150 ms.

## Rules for every string

No em dashes, semicolons, middle dots, tildes as separators, filler, metaphors, slogans or exclamation marks. Units go in column headers. Times are 24-hour with zone (14:32 ET) and dates ISO. Gains and losses always carry a sign or arrow, never color alone. A missing value reads NOT AVAILABLE with its reason. `ui/scripts/screens.mjs` checks the visible text of every screen for banned punctuation on every run.

## Status strip

Always visible: PAPER or SIMULATION, mode in plain words, account, time, feed status, risk service status, API status, theme switch and the kill switch.

## Screens built

Overview, Execution, Reasoning, Research, Composite, News, Earnings, Global, Learn. Not built yet: Opportunities, Markets, Experts, Backtests, Audit and Rules, Settings, the command bar and Guide mode.
