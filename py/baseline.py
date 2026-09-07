"""Untuned baseline: default params on all data, per pair. Writes reports/baseline.md."""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fx.data import PAIRS, load_m15  # noqa: E402
from fx.engine import run  # noqa: E402
from fx.metrics import fmt, monte_carlo_dd, session_label, summary, table  # noqa: E402
from fx.rules import Params, build_features  # noqa: E402

REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")


def main(pairs=None, p: Params = Params(), write=True):
    pairs = pairs or PAIRS
    all_trades = []
    lines = ["# Baseline (untuned defaults: SL 1.5×ATR, TP 2R, ADX>20)\n"]
    for pair in pairs:
        try:
            m15 = load_m15(pair)
        except FileNotFoundError:
            print("missing", pair)
            continue
        t0 = time.time()
        feat = build_features(m15, p)
        tr = run(feat, pair, p)
        days = (m15.index[-1] - m15.index[0]).days * 5 / 7
        s = summary(tr, days)
        print(f"{pair}: {fmt(s)}  sig/day={s['per_day']:.2f}  ({time.time()-t0:.1f}s)", flush=True)
        lines.append(f"- **{pair}** {fmt(s)}  signals/day={s['per_day']:.2f}")
        all_trades.append(tr)
    if not all_trades:
        return None
    t = pd.concat(all_trades, ignore_index=True)
    t["year"] = t["signal_time"].dt.year
    t["weekday"] = t["signal_time"].dt.day_name()
    t["session"] = session_label(t["signal_time"])
    s = summary(t)
    mc = monte_carlo_dd(t["r"].to_numpy())
    print("ALL:", fmt(s), f"MC DD p50={mc['dd_p50']:.1f}R p95={mc['dd_p95']:.1f}R")
    lines += ["", f"**All pairs:** {fmt(s)}", f"Monte Carlo drawdown (1000 shuffles): median {mc['dd_p50']:.1f}R, 95th pct {mc['dd_p95']:.1f}R", ""]
    for by in ("year", "session", "weekday", "dir", "quality"):
        tb = table(t, by)[["trades", "wr", "exp_r", "pf", "max_dd_r", "total_r"]]
        lines += [f"## By {by}", tb.round(3).to_markdown(), ""]
    if write:
        os.makedirs(REPORTS, exist_ok=True)
        open(os.path.join(REPORTS, "baseline.md"), "w").write("\n".join(lines))
        t.to_csv(os.path.join(REPORTS, "baseline_trades.csv"), index=False)
    return t


if __name__ == "__main__":
    main(sys.argv[1:] or None)
