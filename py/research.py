"""Concept research on IN-SAMPLE years only (2019-2022). Holdout 2023-2026 is never touched here.

Each concept: fixed a-priori parameters, same regime/session/volatility filters, same costs, same
throttle and daily stop. Entry modes: market (next open), limit (level, filled if next bar touches),
stop (level, filled if next bar trades through).
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from fx.data import PAIRS, load_m15
from fx.rules import Params, build_features
from fx.engine import COSTS, pip_size
from fx.metrics import summary, fmt
from fx import indicators as ta

IS_START, IS_END = "2019-01-01", "2023-01-01"


def run2(f: pd.DataFrame, pair: str, p: Params, mode: str = "market"):
    """Generic engine. f needs cand_long/cand_short, lvl_long/lvl_short (for limit/stop), atr, swing_low/high, h1_adx."""
    spread_pips, slip_pips = COSTS[pair]
    ps = pip_size(pair)
    spread, slip = spread_pips * ps, slip_pips * ps
    idx = f.index
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr = f["atr"].to_numpy(); swl = f["swing_low"].to_numpy(); swh = f["swing_high"].to_numpy()
    adx = f["h1_adx"].to_numpy(); cl = f["cand_long"].to_numpy(); cs = f["cand_short"].to_numpy()
    lvl_l = f["lvl_long"].to_numpy() if "lvl_long" in f else c
    lvl_s = f["lvl_short"].to_numpy() if "lvl_short" in f else c
    days = idx.normalize().to_numpy()
    n = len(f); trades = []
    open_dir = pending_dir = 0; fill = sl = tp = sl_dist = lvl = 0.0; sig_time = None
    cur_day = None; day_signals = day_losses = 0; day_r = 0.0; day_stopped = False; last_sig = -10**9
    for i in range(n):
        if days[i] != cur_day:
            cur_day = days[i]; day_signals = day_losses = 0; day_r = 0.0; day_stopped = False
        if pending_dir != 0:
            d = pending_dir; pending_dir = 0; filled = False
            if mode == "market":
                fill = o[i] + spread * d; filled = True
            elif mode == "limit":
                if (d > 0 and l[i] <= lvl) or (d < 0 and h[i] >= lvl):
                    px = min(o[i], lvl) if d > 0 else max(o[i], lvl)
                    fill = px + spread * d; filled = True
            elif mode == "stop":
                if (d > 0 and h[i] >= lvl) or (d < 0 and l[i] <= lvl):
                    px = max(o[i], lvl) if d > 0 else min(o[i], lvl)
                    fill = px + spread * d + slip * d; filled = True
            if filled:
                open_dir = d; entry_i = i
                if mode != "market":  # levels relative to fill
                    sl = fill - d * sl_dist; tp = fill + d * p.tp_r * sl_dist
        if open_dir != 0:
            exited = False
            if open_dir > 0:
                if l[i] <= sl: exit_px, exited, outcome = sl - slip, True, "loss"
                elif h[i] >= tp: exit_px, exited, outcome = tp, True, "win"
            else:
                if h[i] >= sl: exit_px, exited, outcome = sl + slip, True, "loss"
                elif l[i] <= tp: exit_px, exited, outcome = tp, True, "win"
            if exited:
                r = (exit_px - fill) / sl_dist * open_dir
                trades.append(dict(pair=pair, dir=open_dir, signal_time=sig_time, entry_time=idx[entry_i], exit_time=idx[i],
                                   fill=fill, sl=sl, tp=tp, exit=exit_px, sl_dist=sl_dist, r=r, outcome=outcome, bars=i - entry_i))
                day_r += r
                if r < 0: day_losses += 1
                if day_losses >= p.max_losses_day or day_r <= p.max_day_r_loss: day_stopped = True
                open_dir = 0
        if open_dir != 0 or pending_dir != 0 or day_stopped: continue
        if day_signals >= p.max_signals_day or i - last_sig < p.min_bars_between: continue
        if not (adx[i] > p.adx_min) or np.isnan(atr[i]) or np.isnan(swl[i]): continue
        if cl[i]:
            d = 1; ref = c[i] if mode == "market" else lvl_l[i]
            sl_dist = max(p.atr_sl_mult * atr[i], ref - swl[i] + p.swing_buffer_atr * atr[i]); lvl = lvl_l[i]
        elif cs[i]:
            d = -1; ref = c[i] if mode == "market" else lvl_s[i]
            sl_dist = max(p.atr_sl_mult * atr[i], swh[i] - ref + p.swing_buffer_atr * atr[i]); lvl = lvl_s[i]
        else:
            continue
        if np.isnan(lvl) or i + 1 >= n: continue
        sl = c[i] - d * sl_dist; tp = c[i] + d * p.tp_r * sl_dist  # market mode; overwritten on fill otherwise
        pending_dir = d; sig_time = idx[i]; last_sig = i; day_signals += 1
    return pd.DataFrame(trades)


def concepts(f: pd.DataFrame, p: Params) -> dict:
    o, h, l, c = f["open"], f["high"], f["low"], f["close"]
    base_l = f["A_long"] & f["D"] & f["E"]
    base_s = f["A_short"] & f["D"] & f["E"]
    out = {}
    # K1 (v1): pullback + confirmation candle, market
    out["K1 v1 confirm-candle (market)"] = (f["cand_long"], f["cand_short"], None, None, "market")
    # K2: limit at EMA20 while price above it (fresh pullback: no touch in last 6 bars)
    above = (c > f["ema20"]) & (l > f["ema20"]) & (ta.barssince(l <= f["ema20"]) >= 6)
    below = (c < f["ema20"]) & (h < f["ema20"]) & (ta.barssince(h >= f["ema20"]) >= 6)
    out["K2 limit @EMA20 pullback"] = (base_l & above, base_s & below, f["ema20"], f["ema20"], "limit")
    # K3: London open range breakout (00:00-07:00 UTC range), stop order, 07:00-10:00 window
    mod = f.index.hour * 60 + f.index.minute
    asian = (mod >= 0) & (mod < 7 * 60)
    day = f.index.normalize()
    rh = h.where(asian).groupby(day).cummax().ffill()
    rl = l.where(asian).groupby(day).cummin().ffill()
    win = (mod >= 7 * 60) & (mod < 10 * 60)
    rng_ok = (rh - rl) < 3 * f["atr"] * 4  # skip if Asian range huge
    k3l = f["A_long"] & f["D"] & win & (c < rh) & rng_ok & (f["h1_adx"] > 0)
    k3s = f["A_short"] & f["D"] & win & (c > rl) & rng_ok
    out["K3 Asian-range breakout (stop)"] = (k3l, k3s, rh + 0.1 * f["atr"], rl - 0.1 * f["atr"], "stop")
    # K4: RSI re-cross in trend direction, market
    rsi = f["rsi"]
    k4l = base_l & (rsi > 35) & (rsi.shift(1) <= 35)
    k4s = base_s & (rsi < 65) & (rsi.shift(1) >= 65)
    out["K4 RSI 35/65 re-cross w/ trend"] = (k4l, k4s, None, None, "market")
    # K5: pullback bar holds EMA20 (touch and close above), market at next open, no breakout requirement
    k5l = base_l & (l <= f["ema20"]) & (c > f["ema20"]) & (c > o) & (c.rolling(6).min() > f["ema50"])
    k5s = base_s & (h >= f["ema20"]) & (c < f["ema20"]) & (c < o) & (c.rolling(6).max() < f["ema50"])
    out["K5 EMA20 touch-and-hold bar (market)"] = (k5l, k5s, None, None, "market")
    # K6: 1H-close breakout of prior 20-bar high in 4H trend (momentum), market
    hh = h.shift(1).rolling(20).max(); ll = l.shift(1).rolling(20).min()
    k6l = base_l & (c > hh) & (c.shift(1) <= hh.shift(1))
    k6s = base_s & (c < ll) & (c.shift(1) >= ll.shift(1))
    out["K6 20-bar high breakout w/ trend"] = (k6l, k6s, None, None, "market")
    return out


def main(pairs=None):
    pairs = pairs or PAIRS
    p = Params()
    feats = {}
    for pair in pairs:
        m = load_m15(pair)
        feats[pair] = build_features(m, p).loc[IS_START:IS_END]
    names = list(concepts(next(iter(feats.values())), p).keys())
    for name in names:
        rows = []
        for pair in pairs:
            f = feats[pair]
            cl, cs, ll, ls, mode = concepts(f, p)[name]
            g = f.copy(); g["cand_long"], g["cand_short"] = cl.fillna(False), cs.fillna(False)
            if ll is not None:
                g["lvl_long"], g["lvl_short"] = ll, ls
            t = run2(g, pair, p, mode)
            rows.append(t)
            print(f"  {pair} {fmt(summary(t))}")
        t = pd.concat(rows, ignore_index=True)
        print(f"{name:40s} IS ALL: {fmt(summary(t))}\n")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
