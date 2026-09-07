import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fx.data import PAIRS, load_m15
from fx import indicators as ta

def scan(start, end, K, entry_minutes, H_list):
    print(f"\n== {start}..{end}  K={K} bars lookback")
    for pair in PAIRS:
        m = load_m15(pair).loc[start:end]
        c = m["close"]; atr = ta.atr(m["high"], m["low"], c, 14)
        mod = m.index.hour * 60 + m.index.minute
        past = (c - c.shift(K)) / atr
        line = f"{pair}: "
        for em in entry_minutes:
            for H in H_list:
                fwd = (c.shift(-H) - c) / atr
                sel = (mod == em) & (m.index.dayofweek < 5)
                x = (-np.sign(past) * fwd)[sel].dropna()   # reversal P&L in ATR units (gross)
                t = x.mean() / (x.std() / np.sqrt(len(x)))
                line += f"{em//60:02d}:{em%60:02d}+{H*15}m n={len(x)} mean={x.mean():+.3f} t={t:+.1f} | "
        print(line)

# entries at 18:00..20:00 with exits BEFORE 21:00 (no rollover overlap)
scan("2019-01-01", "2023-01-01", 8, [18*60, 18*60+30, 19*60, 19*60+30, 20*60], [4])
scan("2019-01-01", "2023-01-01", 8, [18*60, 19*60], [8])
# larger lookback 4h
scan("2019-01-01", "2023-01-01", 16, [19*60, 20*60], [4, 8])
