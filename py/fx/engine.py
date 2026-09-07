"""Path-dependent state loop: Gate B threshold, Gate F throttle, fills, SL/TP resolution, costs.

Fill model (identical to the Pine simulated outcome):
  signal on confirmed bar i  ->  entry at open of bar i+1, plus spread (long: +spread, short: -spread)
  SL / TP levels are computed from the signal bar close (entryRef) and do not move.
  Per bar after entry (including the entry bar): check SL first, then TP. Both in one bar = loss.
  Stop fill = SL -/+ slippage. TP fill = TP exactly.
  R = (exit - fill) / slDist  (planned risk), so spread, gap and slippage show up as R < -1 / < TP_R.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .rules import Params

# pips: spread, slippage
COSTS = {
    "EURUSD": (0.9, 0.3),
    "GBPUSD": (1.3, 0.3),
    "USDJPY": (1.0, 0.3),
    "AUDUSD": (1.1, 0.3),
    "USDCAD": (1.5, 0.3),
}


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def run(feat: pd.DataFrame, pair: str, p: Params = Params(), costs: dict = COSTS) -> pd.DataFrame:
    spread_pips, slip_pips = costs[pair]
    ps = pip_size(pair)
    spread, slip = spread_pips * ps, slip_pips * ps

    idx = feat.index
    o = feat["open"].to_numpy()
    h = feat["high"].to_numpy()
    l = feat["low"].to_numpy()
    c = feat["close"].to_numpy()
    atr = feat["atr"].to_numpy()
    swl = feat["swing_low"].to_numpy()
    swh = feat["swing_high"].to_numpy()
    adx = feat["h1_adx"].to_numpy()
    cl = feat["cand_long"].to_numpy()
    cs = feat["cand_short"].to_numpy()
    ql = feat["Q_long"].to_numpy()
    qs = feat["Q_short"].to_numpy()
    days = idx.normalize().to_numpy()

    n = len(feat)
    trades = []
    # state
    open_dir = 0  # +1 long, -1 short, 0 flat
    pending_dir = 0
    entry_ref = sl = tp = sl_dist = fill = 0.0
    sig_i = -10**9
    sig_time = None
    quality = 0
    cur_day = None
    day_signals = 0
    day_losses = 0
    day_r = 0.0
    day_stopped = False
    last_sig_bar = -10**9

    for i in range(n):
        if days[i] != cur_day:
            cur_day = days[i]
            day_signals = 0
            day_losses = 0
            day_r = 0.0
            day_stopped = False

        # 1. fill pending entry at this bar's open
        if pending_dir != 0:
            open_dir = pending_dir
            pending_dir = 0
            fill = o[i] + spread if open_dir > 0 else o[i] - spread
            entry_i = i

        # 2. manage open trade on this bar (SL first, then TP)
        if open_dir != 0:
            exited = False
            if open_dir > 0:
                if l[i] <= sl:
                    exit_px, exited, outcome = sl - slip, True, "loss"
                elif h[i] >= tp:
                    exit_px, exited, outcome = tp, True, "win"
            else:
                if h[i] >= sl:
                    exit_px, exited, outcome = sl + slip, True, "loss"
                elif l[i] <= tp:
                    exit_px, exited, outcome = tp, True, "win"
            if exited:
                r = (exit_px - fill) / sl_dist * open_dir
                trades.append(
                    dict(
                        pair=pair, dir=open_dir, signal_time=sig_time, entry_time=idx[entry_i], exit_time=idx[i],
                        entry_ref=entry_ref, fill=fill, sl=sl, tp=tp, exit=exit_px, sl_dist=sl_dist,
                        sl_pips=sl_dist / ps, r=r, outcome=outcome, quality=quality, bars=i - entry_i,
                    )
                )
                day_r += r
                if r < 0:
                    day_losses += 1
                if day_losses >= p.max_losses_day or day_r <= p.max_day_r_loss:
                    day_stopped = True
                open_dir = 0

        # 3. new signal on this confirmed bar?
        if open_dir != 0 or pending_dir != 0 or day_stopped:
            continue
        if day_signals >= p.max_signals_day or i - last_sig_bar < p.min_bars_between:
            continue
        if not (adx[i] > p.adx_min):
            continue
        if np.isnan(atr[i]) or np.isnan(swl[i]):
            continue
        if cl[i]:
            d = 1
            sl_dist = max(p.atr_sl_mult * atr[i], c[i] - swl[i] + p.swing_buffer_atr * atr[i])
            sl = c[i] - sl_dist
            tp = c[i] + p.tp_r * sl_dist
            quality = int(ql[i])
        elif cs[i]:
            d = -1
            sl_dist = max(p.atr_sl_mult * atr[i], swh[i] - c[i] + p.swing_buffer_atr * atr[i])
            sl = c[i] + sl_dist
            tp = c[i] - p.tp_r * sl_dist
            quality = int(qs[i])
        else:
            continue
        if i + 1 >= n:
            break
        pending_dir = d
        entry_ref = c[i]
        sig_time = idx[i]
        last_sig_bar = i
        day_signals += 1

    cols = ["pair", "dir", "signal_time", "entry_time", "exit_time", "entry_ref", "fill", "sl", "tp", "exit",
            "sl_dist", "sl_pips", "r", "outcome", "quality", "bars"]
    return pd.DataFrame(trades, columns=cols)
