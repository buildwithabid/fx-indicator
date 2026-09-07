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

---

# Part 2 — ICT / Smart Money Concepts model (added 2026-09-07, same session)

Requested concepts: multi-timeframe bias (5m/1H/4H/Daily), market structure BOS/CHoCH, liquidity sweep,
order-block zone, entry, SL, TP1/TP2/TP3, risk:reward. Implemented deterministically in `py/fx/smc.py`
(swings = pivots confirmed 3 bars later; BOS = close beyond last confirmed swing; CHoCH = BOS against trend;
sweep = wick through a swing low/high with close back inside; displacement = body ≥ 1×ATR closing above the
prior 5-bar high; order block = last opposite candle within 5 bars before displacement, zone = [low, open];
limit entry at zone top valid 12 bars; SL = zone bottom − 0.1 ATR, min 0.8 ATR, max 3 ATR; TP1/2/3 at 1R/2R/3R,
one third each, stop to breakeven after TP1). HTF bias = structure trend on the last closed 1H / 4H / Daily bar.

## In-sample (2019–2022), all 5 pairs
| Variant | Exit | Trades | WR | Exp | PF |
|---|---|---|---|---|---|
| S1 sweep → displacement → OB limit, bias 4H+1H | TP1/2/3 | 211 | 60% | +0.00R | 1.00 |
| S2 same, bias Daily+4H+1H | TP1/2/3 | 142 | 62% | +0.10R | 1.21 |
| S3 same, 15m structure only (no HTF bias) | TP1/2/3 | 495 | 60% | −0.04R | 0.92 |
| **S4 displacement → OB, no sweep required, bias D+4H+1H** | TP1/2/3 | 688 | 63% | **+0.08R** | 1.17 |
| S4 | single TP 2R | 688 | 40% | +0.06R | 1.08 |
| S2 entry at 50% of block | TP1/2/3 | 108 | 69% | +0.05R | 1.12 |
| S4 entry at 50% of block | TP1/2/3 | 548 | 64% | +0.05R | 1.10 |
| Any variant on **5m** entries | any | 271–1534 | 49–56% | **−0.19 … −0.40R** | 0.53–0.75 |

5-minute entries are ruled out: costs are 3–4× larger relative to the stop distance.

## Holdout (2023-01 … 2026-08), run once on the two pre-declared configs
| Config | Trades | WR | Exp | PF | t-stat | Years positive |
|---|---|---|---|---|---|---|
| S4 (best IS sample) | 642 | 58% | **−0.08R** | 0.85 | −1.7 | 0 of 4 |
| S2 (with sweep) | 117 | 58% | −0.06R | 0.89 | −0.5 | 2 of 4 |

The in-sample positive was noise/overfit. The higher win rate (58–63% vs 32% for v1) is an artefact of
scaling out at 1R and moving the stop to breakeven — it does not translate into expectancy. Net of costs
the SMC entries are, like v1, indistinguishable from random.

## Verdict
ICT/SMC concepts did **not** increase accuracy. They are shipped in `dist/smc_indicator.pine` because the
structure/liquidity/order-block visuals, TP1/2/3 levels and R:R are useful for disciplined manual trading,
with the same hard risk controls. They are not a validated edge.
