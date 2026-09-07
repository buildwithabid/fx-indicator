"""Rolling walk-forward: 12-month in-sample, 6-month out-of-sample, step 6 months, 27-combo grid.

Each combo is run once over the full history per pair (daily counters reset each day, so slicing by
window afterwards is equivalent). Selection per window = best IS expectancy with >= 30 trades.
Headline = concatenated OOS trades. Writes reports/walkforward.md.
"""
from __future__ import annotations
import itertools, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fx.data import PAIRS, load_m15
from fx.rules import Params, build_features
from fx.engine import run
from fx.metrics import summary, fmt, monte_carlo_dd

REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
GRID = list(itertools.product((1.2, 1.5, 2.0), (1.5, 2.0, 2.5), (18.0, 20.0, 25.0)))


def main(pairs=None):
    pairs = pairs or PAIRS
    feats = {pair: build_features(load_m15(pair)) for pair in pairs}
    results = {}
    for combo in GRID:
        p = Params(atr_sl_mult=combo[0], tp_r=combo[1], adx_min=combo[2])
        results[combo] = pd.concat([run(feats[pair], pair, p) for pair in pairs], ignore_index=True)
        print(f"grid {combo}: {fmt(summary(results[combo]))}", flush=True)

    windows = []
    start = pd.Timestamp("2019-01-01", tz="UTC")
    while True:
        is0, is1 = start, start + pd.DateOffset(months=12)
        oos0, oos1 = is1, is1 + pd.DateOffset(months=6)
        if oos0 >= pd.Timestamp("2026-09-01", tz="UTC"):
            break
        windows.append((is0, is1, oos0, min(oos1, pd.Timestamp("2026-09-01", tz="UTC"))))
        start += pd.DateOffset(months=6)

    lines = ["# Walk-forward (12m IS / 6m OOS, step 6m; grid = SL mult × TP R × ADX min, 27 combos)\n",
             "| # | IS | OOS | chosen (SL,TP,ADX) | IS exp | OOS trades | OOS WR | OOS exp | OOS PF |", "|---|---|---|---|---|---|---|---|---|"]
    oos_all, chosen_counts = [], {}
    for k, (is0, is1, oos0, oos1) in enumerate(windows, 1):
        best, best_s = None, None
        for combo, t in results.items():
            s = summary(t[(t.signal_time >= is0) & (t.signal_time < is1)])
            if s["trades"] >= 30 and (best is None or s["exp_r"] > best_s["exp_r"]):
                best, best_s = combo, s
        if best is None:
            continue
        chosen_counts[best] = chosen_counts.get(best, 0) + 1
        t = results[best]
        oos = t[(t.signal_time >= oos0) & (t.signal_time < oos1)]
        so = summary(oos)
        oos_all.append(oos)
        lines.append(f"| {k} | {is0:%Y-%m}–{is1:%Y-%m} | {oos0:%Y-%m}–{oos1:%Y-%m} | {best} | {best_s['exp_r']:+.3f} | {so['trades']} | "
                     f"{so['wr']*100:.0f}% | {so['exp_r']:+.3f} | {so['pf']:.2f} |")
    oos = pd.concat(oos_all, ignore_index=True)
    s = summary(oos); mc = monte_carlo_dd(oos["r"].to_numpy())
    pos_windows = sum(1 for o in oos_all if summary(o)["exp_r"] > 0.1 and summary(o)["pf"] > 1.2)
    lines += ["", f"**Concatenated OOS:** {fmt(s)}", f"Monte Carlo DD: median {mc['dd_p50']:.1f}R, p95 {mc['dd_p95']:.1f}R",
              f"Windows passing (OOS exp > 0.1R and PF > 1.2): {pos_windows} of {len(oos_all)}",
              f"Combos chosen: {chosen_counts}", "",
              "## Every grid point over the full history (for the overfitting check)", "| SL | TP | ADX | trades | WR | exp | PF | maxDD |", "|---|---|---|---|---|---|---|---|"]
    for combo, t in results.items():
        s = summary(t)
        lines.append(f"| {combo[0]} | {combo[1]} | {combo[2]} | {s['trades']} | {s['wr']*100:.1f}% | {s['exp_r']:+.3f} | {s['pf']:.2f} | {s['max_dd_r']:.1f} |")
    os.makedirs(REPORTS, exist_ok=True)
    open(os.path.join(REPORTS, "walkforward.md"), "w").write("\n".join(lines))
    print("\n".join(lines[-40:]))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
