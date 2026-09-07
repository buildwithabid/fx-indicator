# Rules v1 (frozen 2026-09-07)

Everything below is fixed before any backtest. Only three parameters are tuned in walk-forward:
`ATR_SL_MULT ∈ {1.2, 1.5, 2.0}`, `TP_R ∈ {1.5, 2.0, 2.5}`, `ADX_MIN ∈ {18, 20, 25}`.
Defaults: 1.5 / 2.0 / 20.

Long side is specified; short is the exact mirror (swap >/<, high/low, EMA order, RSI 70 → 30).

## Data conventions
- Chart timeframe 15m. Higher timeframes (HTF) 1H and 4H are built from the same feed, UTC-anchored
  (4H bars open at 00/04/08/12/16/20 UTC). On TradingView use `FX:EURUSD` etc. (FXCM feed, UTC-aligned 4H).
- HTF values are taken from the **last closed** HTF bar. In Pine: `request.security(sym, tf, expr[1], lookahead=barmerge.lookahead_on)`.
  In Python: resample, shift by one HTF bar, forward-fill onto 15m bars, and only use values whose HTF bar close time ≤ current 15m bar open time.
- All indicator maths use Pine seeding: EMA = `ewm(span=n, adjust=False)`; RMA (ATR, ADX, RSI) = `ewm(alpha=1/n, adjust=False)`.
- Signals are evaluated on the **close of a confirmed 15m bar**; entry is the **open of the next bar**.

## Gates (ALL must be true)

### A. 4H regime
`ema50_4h > ema200_4h` and `close_4h > ema50_4h` (last closed 4H bar).

### B. 1H strength
`adx14_1h > ADX_MIN` (last closed 1H bar). ADX uses Wilder RMA smoothing for TR, +DM, -DM and DX.

### C. 15m pullback + confirmation
- Pullback: within the last 6 bars **including the current bar**, `low <= ema20_15m` at least once (`barssince(low <= ema20) <= 5`).
- Structure intact: lowest close over the same 6 bars `> ema50_15m` (current value).
- Confirmation bar (current): `close > open`, `close > high[1]`, `(close - open) >= 0.5 * (high - low)`, `high - low > 0`.
- Overbought veto: `rsi14_15m < 70`.

### D. Volatility
- `atr14_15m` between the 20th and 95th percentile (nearest-rank) of the last 480 bars of atr14 (inclusive of the current bar).
- Spike cooldown: none of the last 4 bars (current + 3 previous) has `(high - low) > 3 * atr14[1]`.

### E. Session (all UTC)
- Allowed windows: 07:15–10:45 and 13:45–16:00 (bar **open** time inside window, end exclusive).
- Blocked: Friday from 15:00; all Sunday; Monday before 07:15.
- News blackout (daily, bar open time inside window is blocked): default `12:25–13:05, 13:55–14:20`.
- Extra blackout dates (whole day blocked): input list of `YYYY-MM-DD`, default empty. User maintains from ForexFactory (NFP, FOMC, CPI).

### F. Throttle
- Max 2 signals per pair per UTC day.
- At least 8 bars since the last signal bar.
- No new signal while a simulated trade is open.
- Daily stop: no signals for the rest of the UTC day after 2 simulated losses, or once the day's realised R ≤ −2.
- Counters reset at the UTC day boundary.

## Risk per signal (long)
```
atr      = atr14_15m (current bar)
swingLow = lowest(low, 10)   (current + 9 previous)
slDist   = max(ATR_SL_MULT * atr, close - swingLow + 0.1 * atr)
entryRef = close of signal bar   (Pine label/alert shows this; fill is next open)
SL       = entryRef - slDist
TP       = entryRef + TP_R * slDist
```
Fill model (Python and simulated outcome in Pine): entry = next bar open + spread; stop exit = SL − slippage; TP exit = TP.
Outcome resolution per bar after entry: check SL first (`low <= SL`), then TP (`high >= TP`). Same-bar both = loss.
No time stop in v1 (trade runs until SL or TP).

Lot size (USD account):
```
pipSize        = mintick * 10            (0.0001 majors, 0.01 JPY pairs)
slPips         = slDist / pipSize
pipValuePerLot = 100000 * pipSize / quoteToUsd   (quoteToUsd = 1 for xxxUSD; = USDJPY price for USDJPY; = USDCAD price for USDCAD)
lots           = floor((equity * riskPct/100) / (slPips * pipValuePerLot) * 100) / 100
```

## Costs (Python backtest), pips
| Pair | Spread | Slippage (entry and stop, each) |
|---|---|---|
| EURUSD | 0.9 | 0.3 |
| GBPUSD | 1.3 | 0.3 |
| USDJPY | 1.0 | 0.3 |
| AUDUSD | 1.1 | 0.3 |
| USDCAD | 1.5 | 0.3 |

## Quality badge (display only, 0–3)
+1 if 40 ≤ rsi14 ≤ 60; +1 if the pullback low stayed above ema50 by ≥ 0.25·atr; +1 if confirmation body ≥ 0.7·range.
