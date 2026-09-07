"""Diagnostic: expectancy of the entry with different gate subsets (analysis, not tuning)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from fx.data import load_m15
from fx.rules import Params, build_features
from fx.engine import run
from fx.metrics import summary, fmt

pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
p = Params()
m = load_m15(pair)
f = build_features(m, p)
base_long, base_short = f["C_long"], f["C_short"]
combos = {
    "C only (pullback+confirm)": (base_long, base_short),
    "C+E (session)": (base_long & f["E"], base_short & f["E"]),
    "C+A (4H regime)": (base_long & f["A_long"], base_short & f["A_short"]),
    "C+D (vol)": (base_long & f["D"], base_short & f["D"]),
    "C+A+E": (base_long & f["A_long"] & f["E"], base_short & f["A_short"] & f["E"]),
    "C+A+D+E (all, B in engine)": (f["cand_long"], f["cand_short"]),
}
for adx_min in (0.0, 20.0):
    pp = Params(adx_min=adx_min)
    print(f"--- ADX min {adx_min}")
    for name, (cl, cs) in combos.items():
        g = f.copy(); g["cand_long"], g["cand_short"] = cl, cs
        t = run(g, pair, pp)
        print(f"{name:32s} {fmt(summary(t))}")
