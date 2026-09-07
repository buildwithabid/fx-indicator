# Risk-Averse FX Day Trader v1

TradingView (Pine v6) indicator + strategy for the majors on 15-minute charts, with 1H/4H trend gating,
ATR/structure stops, position sizing, session and news blackouts, and a daily loss limit that silences it.
A Python backtest of the identical rules on 7.7 years of free M15 data lives in `py/`.

## Read this first — what the backtest says
**The rules have no edge.** Over 2019-01 … 2026-08, all five pairs, after realistic spread + slippage:

| | Trades | Win rate | Expectancy | Profit factor |
|---|---|---|---|---|
| v1 rules (untuned) | 1,367 | 32.3% | −0.118R | 0.84 |
| Random entries, same engine | 617 | 33.1% | −0.102R | 0.86 |
| Walk-forward tuned, out-of-sample | 1,194 | 31.7% | −0.145R | 0.80 |

Eight alternative entry concepts and two exit schemes were also tested in-sample; none was positive
(`reports/research.md`). What the tool *does* deliver: non-repainting signals, a hard stop and target on every
signal, correct lot size for a fixed % risk, no signals in the Asian session / late Friday / around scheduled US
data, and a hard daily stop. Treat it as a discipline layer around your own decisions, not as a money machine.

## Files
- `dist/indicator.pine` — paste into TradingView Pine Editor (Indicators). Generated from `pine/core.pine`.
- `dist/strategy.pine` — same logic as a strategy for the built-in tester and trade-list export.
- `spec/rules_v1.md` — the frozen rule set (single source of truth).
- `py/` — data fetch, indicators matching Pine maths, rules, engine, metrics, baseline, walk-forward, parity.
- `reports/` — `baseline.md`, `walkforward.md`, `research.md`, `baseline_trades.csv`.

## Using the indicator on TradingView
1. Open a 15m chart of `FX:EURUSD` (or `FX:GBPUSD`, `FX:USDJPY`, `FX:AUDUSD`, `FX:USDCAD`). Use the `FX:` feed:
   its 4H bars are UTC-aligned, matching the backtest. OANDA/other feeds align 4H bars to 17:00 New York, which
   shifts the regime gate.
2. Pine Editor → paste `dist/indicator.pine` → Add to chart.
3. Settings → **Risk**: set equity and risk %; for USDJPY/USDCAD the pip value is converted automatically for a
   USD account. **Filters**: times are UTC; add news dates (NFP, FOMC, CPI) from ForexFactory as `YYYY-MM-DD`,
   comma-separated. **Display**: timezone for the table (default Asia/Karachi).
4. Alerts (free plan, no webhooks): right-click chart → Add alert → Condition = this indicator → "Any alert()
   function call" (dynamic message with entry/SL/TP/lots) or "Any signal" (static). Delivery: TradingView app push
   + email.
5. The label on each signal shows entry (signal-bar close), stop, target, stop distance in pips, lot size and a
   0–3 quality badge. Fill is assumed at the next bar open plus the spread input.
6. The table shows regime, ADX, ATR band, session state, today's signals/losses, and the simulated running W/L
   of the indicator's own signals (SL is checked before TP inside a bar, i.e. worst case).

Non-repainting: HTF values use the last *closed* 1H/4H bar; all state updates only on confirmed bars.

## Python
```
uv venv py/.venv --python 3.13 && uv pip install --python py/.venv/bin/python -r py/requirements.txt
py/.venv/bin/python py/data/fetch_histdata.py          # ~2 min, histdata.com M1 → M15 UTC CSVs
py/.venv/bin/python -m pytest -q py/tests               # indicator maths vs Pine formulas
py/.venv/bin/python py/baseline.py                      # reports/baseline.md
py/.venv/bin/python py/walkforward.py                   # reports/walkforward.md
py/.venv/bin/python py/research.py                      # in-sample concept comparison
py/.venv/bin/python pine/build.py                       # regenerate dist/*.pine after editing pine/core.pine
py/.venv/bin/python py/parity.py EURUSD trades.csv chart.csv   # after exporting from TradingView (see file)
```
Data: histdata.com timestamps are EST without DST; the fetcher shifts them +5h to UTC. Quotes are bid.

## Costs assumed (pips)
EURUSD 0.9, GBPUSD 1.3, USDJPY 1.0, AUDUSD 1.1, USDCAD 1.5 spread, plus 0.3 slippage on entry and on stop.

## Known limitations
- Pine's strategy tester resolves same-bar SL+TP optimistically and has no spread; the `slippage=7` setting in
  `dist/strategy.pine` approximates costs. Python numbers are the reference.
- News blackouts are time-of-day windows plus a manual date list; Pine has no economic calendar.
- The 3×ATR spike cooldown only reacts *after* a news candle.
- Parity test (`py/parity.py`) needs the user's TradingView CSV exports; it has not yet been run.
