"""ICT / Smart Money Concepts features, deterministic and non-repainting.

Swings: pivot highs/lows confirmed N bars after the fact (Pine ta.pivothigh(N,N)).
Structure: trend = direction of the last Break Of Structure (close beyond the last confirmed, unbroken
swing). A BOS against the current trend is a CHoCH (change of character) and flips the trend.
Liquidity sweep: low wicks below the last confirmed swing low but the bar closes back above it (bullish);
mirror for highs.
Displacement: strong candle (body >= disp_atr * ATR) closing above the highest high of the prior `disp_look`
bars (bullish) within `sweep_valid` bars after a sweep -> this is the BOS candle.
Order block: last bearish candle within `ob_look` bars before the displacement candle; zone = [low, open].
Entry: limit at the zone top, valid `ob_valid` bars. SL = zone bottom - buf*ATR. TP1/2/3 at 1R/2R/3R.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def pivots(h: np.ndarray, l: np.ndarray, n: int):
    """Returns arrays ph, pl: at bar i (>= n), value of pivot high/low confirmed at bar i (occurred at i-n), else nan."""
    m = len(h)
    ph = np.full(m, np.nan); pl = np.full(m, np.nan)
    for i in range(n, m - 0):
        k = i - n
        if k - n < 0:
            continue
        seg_h = h[k - n : k + n + 1]; seg_l = l[k - n : k + n + 1]
        if h[k] == seg_h.max() and (seg_h == h[k]).sum() == 1:
            ph[i] = h[k]
        if l[k] == seg_l.min() and (seg_l == l[k]).sum() == 1:
            pl[i] = l[k]
    return ph, pl


def structure(c: np.ndarray, h: np.ndarray, l: np.ndarray, n: int):
    """Per bar: trend (+1/-1/0), last unbroken swing high/low levels, bos_up/bos_dn flags, sweep_lo/sweep_hi flags."""
    m = len(c)
    ph, pl = pivots(h, l, n)
    trend = np.zeros(m, dtype=int)
    last_sh = np.full(m, np.nan); last_sl = np.full(m, np.nan)
    bos_up = np.zeros(m, dtype=bool); bos_dn = np.zeros(m, dtype=bool)
    sweep_lo = np.zeros(m, dtype=bool); sweep_hi = np.zeros(m, dtype=bool)
    sh = np.nan; sl = np.nan; t = 0
    for i in range(m):
        # sweep test against the swing levels known BEFORE this bar
        if not np.isnan(sl) and l[i] < sl and c[i] > sl:
            sweep_lo[i] = True
        if not np.isnan(sh) and h[i] > sh and c[i] < sh:
            sweep_hi[i] = True
        # BOS on close
        if not np.isnan(sh) and c[i] > sh:
            bos_up[i] = True; t = 1; sh = np.nan
        if not np.isnan(sl) and c[i] < sl:
            bos_dn[i] = True; t = -1; sl = np.nan
        # new confirmed pivots (occurred n bars ago) become the reference levels
        if not np.isnan(ph[i]):
            sh = ph[i] if np.isnan(sh) else ph[i]  # most recent confirmed swing high
        if not np.isnan(pl[i]):
            sl = pl[i]
        trend[i] = t; last_sh[i] = sh; last_sl[i] = sl
    return dict(trend=trend, last_sh=last_sh, last_sl=last_sl, bos_up=bos_up, bos_dn=bos_dn, sweep_lo=sweep_lo, sweep_hi=sweep_hi)


def add_smc(df: pd.DataFrame, n: int = 3, disp_atr: float = 1.0, disp_look: int = 5, sweep_valid: int = 8,
            ob_look: int = 5) -> pd.DataFrame:
    """Adds 15m SMC columns: trend, sweep flags, displacement flags, OB zone (top/bottom) at displacement bars."""
    h, l, c, o = (df[k].to_numpy() for k in ("high", "low", "close", "open"))
    atr = df["atr"].to_numpy()
    s = structure(c, h, l, n)
    m = len(df)
    body = np.abs(c - o)
    hh_prev = pd.Series(h).shift(1).rolling(disp_look).max().to_numpy()
    ll_prev = pd.Series(l).shift(1).rolling(disp_look).min().to_numpy()
    disp_up = (c > o) & (body >= disp_atr * atr) & (c > hh_prev)
    disp_dn = (c < o) & (body >= disp_atr * atr) & (c < ll_prev)
    # bars since last sweep
    idx = np.arange(m)
    def since(flag):
        last = pd.Series(np.where(flag, idx, np.nan)).ffill().to_numpy()
        return idx - last
    since_swlo = since(s["sweep_lo"]); since_swhi = since(s["sweep_hi"])
    setup_long = disp_up & (since_swlo <= sweep_valid) & (since_swlo >= 1)
    setup_short = disp_dn & (since_swhi <= sweep_valid) & (since_swhi >= 1)
    ob_top = np.full(m, np.nan); ob_bot = np.full(m, np.nan)
    for i in np.where(setup_long)[0]:
        for k in range(i - 1, max(i - 1 - ob_look, -1), -1):
            if c[k] < o[k]:
                ob_top[i] = o[k]; ob_bot[i] = l[k]; break
    for i in np.where(setup_short)[0]:
        for k in range(i - 1, max(i - 1 - ob_look, -1), -1):
            if c[k] > o[k]:
                ob_top[i] = h[k]; ob_bot[i] = o[k]; break
    ob_top_any = np.full(m, np.nan); ob_bot_any = np.full(m, np.nan)
    for i in np.where(disp_up)[0]:
        for k in range(i - 1, max(i - 1 - ob_look, -1), -1):
            if c[k] < o[k]:
                ob_top_any[i] = o[k]; ob_bot_any[i] = l[k]; break
    for i in np.where(disp_dn)[0]:
        for k in range(i - 1, max(i - 1 - ob_look, -1), -1):
            if c[k] > o[k]:
                ob_top_any[i] = h[k]; ob_bot_any[i] = o[k]; break
    out = df.copy()
    out["ob_top_any"] = ob_top_any; out["ob_bot_any"] = ob_bot_any
    out["s_trend"] = s["trend"]; out["s_last_sh"] = s["last_sh"]; out["s_last_sl"] = s["last_sl"]
    out["bos_up"] = s["bos_up"]; out["bos_dn"] = s["bos_dn"]
    out["sweep_lo"] = s["sweep_lo"]; out["sweep_hi"] = s["sweep_hi"]
    out["disp_up"] = disp_up; out["disp_dn"] = disp_dn
    out["setup_long"] = setup_long & ~np.isnan(ob_top); out["setup_short"] = setup_short & ~np.isnan(ob_top)
    out["ob_top"] = ob_top; out["ob_bot"] = ob_bot
    return out


def htf_bias(m15: pd.DataFrame, rule: str, n: int) -> pd.Series:
    """Structure trend on a higher timeframe, aligned to 15m bars using the LAST CLOSED HTF bar."""
    from .data import resample, align_htf_last_closed
    htf = resample(m15[["open", "high", "low", "close"]], rule)
    s = structure(htf["close"].to_numpy(), htf["high"].to_numpy(), htf["low"].to_numpy(), n)
    htf["bias"] = s["trend"]
    return align_htf_last_closed(m15.index, htf, ["bias"], rule)["bias"]
