# Research log — concepts tested and why v1 has no edge (2026-09-07)

All tests: 5 majors, 15m bars from histdata.com (M1 bid → M15, UTC), costs = spread + 0.3 pip slippage per side
(EURUSD 0.9, GBPUSD 1.3, USDJPY 1.0, AUDUSD 1.1, USDCAD 1.5 pips), same 4H-regime / ATR-band / session filters,
same throttle and daily stop. In-sample (IS) = 2019-01 … 2022-12. Holdout 2023-01 … 2026-08 was only used by
the baseline and walk-forward runs of v1, never for concept selection.

## Engine sanity
| Signal | Trades | WR | Expectancy |
|---|---|---|---|
| Random entries (2% of session bars) | 617 | 33.1% | −0.102R |
| Look-ahead (knows next 3h) | 2764 | 67.6% | +0.926R |
| **v1 rules** | 274 | 32.5% | **−0.101R** |

Random and v1 are indistinguishable: the cost drag is ≈0.10–0.13R per trade, and the v1 entry has zero gross edge.

## Concepts (IS, all 5 pairs pooled)
| # | Concept | Trades | WR | Exp | PF |
|---|---|---|---|---|---|
| K1 | v1: pullback to EMA20 + confirmation candle (close > prior high), market | 722 | 32.7% | −0.104R | 0.86 |
| K2 | Limit order at EMA20 on a fresh pullback in 4H trend | 167 | 28.7% | −0.158R | 0.78 |
| K3 | Asian-range (00–07 UTC) breakout at London open, stop order | 310 | 31.3% | −0.074R | 0.89 |
| K4 | RSI 35/65 re-cross in trend direction | 766 | 34.7% | −0.068R | 0.91 |
| K5 | EMA20 touch-and-hold bar, market | 912 | 33.3% | −0.106R | 0.86 |
| K6 | 20-bar high/low breakout in 4H trend | 984 | 32.7% | −0.076R | 0.89 |
| K1 + chandelier 2×ATR trailing exit (no TP) | | 808 | 31.8% | −0.099R | 0.75 |
| K1 + exit on close back through EMA20 | | 794 | 25.9% | −0.093R | 0.79 |
| K1 on 1H bars (07–16 UTC, 1 trade/day) | | 368 | 35.6% | +0.021R | 1.03 |

Grid sweep of the three tunable parameters for v1 on EURUSD (12 points): every point negative (−0.02R … −0.12R).

## Time-of-day scan (IS)
Momentum/reversal t-stats by UTC hour (sign of last 2h move × next 3h move, ATR units). London/NY morning hours
(07–16 UTC) show nothing consistent across pairs. Hours 19–22 UTC show a very strong *reversal* (t = −4 … −10 on
all 5 pairs, every year). **It is an artifact**: it disappears when the forward window ends before 21:00 UTC
(t ≈ 0 … +2, mean ≈ 0.03 ATR ≈ 0.2 pip). It comes from bid-only quotes dropping when spreads widen into the
21:00–22:00 UTC rollover and recovering afterwards. Not tradable. Documented so nobody rediscovers it.

## Walk-forward of v1 (reports/walkforward.md)
14 rolling windows (12m IS / 6m OOS), 27-combo grid. Concatenated OOS: 1194 trades, WR 31.7%, −0.145R, PF 0.80.
Windows passing (OOS exp > 0.1R and PF > 1.2): 1 of 14. Chosen parameters jump around every window — noise.

## Conclusion
No rule set tested has a positive expectancy on 15m majors after realistic costs. The indicator as shipped is a
non-repainting **risk-management and discipline tool** (hard SL/TP, position size, session and news gating, daily
loss limit), not a proven signal source. Do not size it as if it had an edge. See README for what would be needed
to change that conclusion.
