"""Indicator maths matching TradingView Pine Script v6 semantics.

Pine seeding rules reproduced here:
  ta.ema(src, n)  -> alpha = 2/(n+1); first value = src[0]           (pandas ewm span=n, adjust=False)
  ta.rma(src, n)  -> alpha = 1/n;     Pine seeds with SMA(n) of the first n values, then RMA.
  ta.atr(n)       -> rma(tr, n) with tr = max(h-l, |h-c1|, |l-c1|); first tr = h-l
  ta.rsi(src, n)  -> rma of up / rma of down (Pine's rma seeding)
  ta.adx / dmi    -> Pine's ta.dmi: rma(tr), rma(+dm), rma(-dm) -> di; dx; adx = rma(dx, adxLen)
  ta.percentile_nearest_rank(src, n, pct)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Pine ta.rma: first defined value is SMA of first n non-NaN values, then Wilder smoothing."""
    v = s.to_numpy(dtype=float)
    out = np.full(v.shape, np.nan)
    alpha = 1.0 / n
    start = 0
    while start < len(v) and np.isnan(v[start]):
        start += 1
    if len(v) - start < n:
        return pd.Series(out, index=s.index)
    i = start + n - 1
    out[i] = np.nanmean(v[start : i + 1])
    for j in range(i + 1, len(v)):
        x = v[j]
        if np.isnan(x):
            out[j] = out[j - 1]
        else:
            out[j] = alpha * x + (1 - alpha) * out[j - 1]
    return pd.Series(out, index=s.index)


def true_range(h: pd.Series, l: pd.Series, c: pd.Series) -> pd.Series:
    c1 = c.shift(1)
    tr = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1)
    tr.iloc[0] = (h - l).iloc[0]
    return tr


def atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    return rma(true_range(h, l, c), n)


def rsi(src: pd.Series, n: int = 14) -> pd.Series:
    d = src.diff()
    up = d.clip(lower=0)
    dn = (-d).clip(lower=0)
    up.iloc[0] = np.nan
    dn.iloc[0] = np.nan
    ru = rma(up, n)
    rd = rma(dn, n)
    out = 100 - 100 / (1 + ru / rd)
    out = out.where(rd != 0, 100.0)
    out = out.where(~((ru == 0) & (rd == 0)), 50.0)  # Pine returns NaN-ish; flat data is edge case
    return out


def adx(h: pd.Series, l: pd.Series, c: pd.Series, di_len: int = 14, adx_len: int = 14) -> pd.Series:
    """Pine: [diplus, diminus, adx] = ta.dmi(diLen, adxLen)."""
    up = h.diff()
    dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=h.index)
    plus_dm.iloc[0] = np.nan
    minus_dm.iloc[0] = np.nan
    tr = true_range(h, l, c)
    tr.iloc[0] = np.nan  # Pine ta.dmi: first bar tr is na because of na close[1]
    trr = rma(tr, di_len)
    plus = 100 * rma(plus_dm, di_len) / trr
    minus = 100 * rma(minus_dm, di_len) / trr
    s = plus + minus
    dx = (100 * (plus - minus).abs() / s.where(s != 0, np.nan)).fillna(0.0)
    dx[trr.isna()] = np.nan
    return rma(dx, adx_len)


def percentile_nearest_rank(s: pd.Series, n: int, pct: float) -> pd.Series:
    """Pine ta.percentile_nearest_rank over the last n values (inclusive of current)."""
    k = int(np.ceil(pct / 100.0 * n))  # 1-based rank
    k = max(1, min(n, k))

    def f(w):
        return np.sort(w)[k - 1]

    return s.rolling(n, min_periods=n).apply(f, raw=True)


def lowest(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).min()


def highest(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).max()


def barssince(cond: pd.Series) -> pd.Series:
    """Bars since cond was last true (0 if true now). NaN before first true."""
    idx = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), idx, np.nan), index=cond.index).ffill()
    return pd.Series(idx, index=cond.index) - last
