"""Scan (IS only): does the return over the prior K hours predict the next H hours, by UTC hour? t-stats."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fx.data import PAIRS, load_m15
from fx import indicators as ta

K, H = 8, 12   # prior 2h (8 bars), forward 3h (12 bars)
rows = []
for pair in PAIRS:
    m = load_m15(pair).loc["2019-01-01":"2023-01-01"]
    c = m["close"]; atr = ta.atr(m["high"], m["low"], c, 14)
    past = (c - c.shift(K)) / atr
    fwd = (c.shift(-H) - c) / atr
    df = pd.DataFrame({"past": past, "fwd": fwd, "hour": m.index.hour, "year": m.index.year, "dow": m.index.dayofweek}).dropna()
    df = df[df.dow < 5]
    for hr, g in df.groupby("hour"):
        # momentum strategy: sign(past) * fwd
        x = np.sign(g["past"]) * g["fwd"]
        t = x.mean() / (x.std() / np.sqrt(len(x)))
        by_year = (np.sign(g["past"]) * g["fwd"]).groupby(g["year"]).mean()
        rows.append(dict(pair=pair, hour=hr, n=len(x), mom_mean=x.mean(), t=t, years_pos=int((by_year > 0).sum())))
r = pd.DataFrame(rows)
piv = r.pivot(index="hour", columns="pair", values="t").round(1)
piv["avg_t"] = piv.mean(axis=1).round(2)
print("t-stat of momentum (sign of last 2h return x next 3h return, ATR units) by UTC hour, IS 2019-2022")
print(piv.to_string())
print("\nyears positive (of 4) for momentum, by hour:")
print(r.pivot(index="hour", columns="pair", values="years_pos").to_string())
