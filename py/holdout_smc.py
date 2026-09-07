"""ONE-TIME holdout (2023-01 .. 2026-08) of the pre-declared SMC configs. Do not iterate on this."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd, numpy as np
from fx.data import PAIRS
from fx.rules import Params
from fx.metrics import summary, fmt, monte_carlo_dd, table
from research_smc import build, variants, run_smc

OOS = ("2023-01-01", "2026-09-01")
p = Params()
feats = {pair: build(pair, lo=OOS[0], hi=OOS[1]) for pair in PAIRS}
for name in ("S4 displacement->OB without sweep, bias D+4H+1H", "S2 same, bias D+4H+1H"):
    rows = []
    for pair in PAIRS:
        f = feats[pair]; cl, cs = variants(f)[name]
        g = f.copy(); g["cand_long"] = cl.fillna(False); g["cand_short"] = cs.fillna(False)
        if name.startswith("S4"):
            g["ob_top"] = g["ob_top_any"]; g["ob_bot"] = g["ob_bot_any"]
        t = run_smc(g, pair, p, entry="ob_top", tps=(1.0, 2.0, 3.0), be_after_tp1=True); rows.append(t)
    t = pd.concat(rows, ignore_index=True); t["year"] = t.signal_time.dt.year
    s = summary(t); mc = monte_carlo_dd(t.r.to_numpy())
    r = t.r.to_numpy(); tstat = r.mean() / (r.std() / np.sqrt(len(r)))
    print(f"HOLDOUT {name}\n   {fmt(s)}  t={tstat:.2f}  MC DD p50={mc['dd_p50']:.1f} p95={mc['dd_p95']:.1f}")
    print(table(t, "pair")[["trades", "wr", "exp_r", "pf", "max_dd_r", "total_r"]].round(3).to_string())
    print(table(t, "year")[["trades", "wr", "exp_r", "pf", "total_r"]].round(3).to_string())
    t.to_csv(f"reports/holdout_{name[:2]}_trades.csv", index=False)
