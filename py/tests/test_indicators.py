"""Check vectorised indicators against literal bar-by-bar transcriptions of Pine's built-in sources.

Pine v6 reference implementations (from TradingView docs / built-in source):
  ta.ema: alpha = 2/(n+1); sum := na(sum[1]) ? src : alpha*src + (1-alpha)*nz(sum[1])
  ta.rma: alpha = 1/n;     sum := na(sum[1]) ? ta.sma(src, n) : alpha*src + (1-alpha)*nz(sum[1])
  ta.atr: rma(tr(true), n)
  ta.rsi: 100 - 100/(1 + rma(max(chg,0), n)/rma(-min(chg,0), n))
  ta.dmi: see below
"""
import math
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fx import indicators as ta  # noqa: E402


def _ohlc(n=600, seed=1):
    rng = np.random.default_rng(seed)
    c = 1.1 + np.cumsum(rng.normal(0, 0.0005, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 0.0004, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.0004, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


def pine_ema(src, n):
    a = 2 / (n + 1)
    out = []
    s = None
    for x in src:
        s = x if s is None else a * x + (1 - a) * s
        out.append(s)
    return np.array(out)


def pine_rma(src, n):
    a = 1 / n
    out = []
    s = None
    buf = []
    for x in src:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            out.append(np.nan)
            continue
        buf.append(x)
        if s is None:
            if len(buf) < n:
                out.append(np.nan)
                continue
            s = sum(buf[-n:]) / n
        else:
            s = a * x + (1 - a) * s
        out.append(s)
    return np.array(out)


def pine_tr(h, l, c, handle_na):
    out = []
    for i in range(len(h)):
        if i == 0:
            out.append(h[0] - l[0] if handle_na else np.nan)
        else:
            out.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return out


def test_ema():
    df = _ohlc()
    v = ta.ema(df["close"], 20).to_numpy()
    r = pine_ema(df["close"].to_numpy(), 20)
    assert np.allclose(v, r, atol=1e-12)


def test_rma_atr():
    df = _ohlc()
    v = ta.atr(df["high"], df["low"], df["close"], 14).to_numpy()
    r = pine_rma(pine_tr(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), True), 14)
    assert np.allclose(v[13:], r[13:], atol=1e-12)
    assert np.isnan(v[:13]).all()


def test_rsi():
    df = _ohlc()
    c = df["close"].to_numpy()
    chg = [np.nan] + [c[i] - c[i - 1] for i in range(1, len(c))]
    up = [np.nan if math.isnan(x) else max(x, 0) for x in chg]
    dn = [np.nan if math.isnan(x) else max(-x, 0) for x in chg]
    ru, rd = pine_rma(up, 14), pine_rma(dn, 14)
    ref = 100 - 100 / (1 + ru / rd)
    v = ta.rsi(df["close"], 14).to_numpy()
    m = ~np.isnan(ref)
    assert np.allclose(v[m], ref[m], atol=1e-9)


def test_adx():
    df = _ohlc()
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(h)
    up = [np.nan] + [h[i] - h[i - 1] for i in range(1, n)]
    dn = [np.nan] + [-(l[i] - l[i - 1]) for i in range(1, n)]
    plus_dm = [np.nan if math.isnan(u) else (u if (u > d and u > 0) else 0.0) for u, d in zip(up, dn)]
    minus_dm = [np.nan if math.isnan(d) else (d if (d > u and d > 0) else 0.0) for u, d in zip(up, dn)]
    trur = pine_rma(pine_tr(h, l, c, False), 14)
    plus = 100 * pine_rma(plus_dm, 14) / trur
    minus = 100 * pine_rma(minus_dm, 14) / trur
    s = plus + minus
    dx = [np.nan if math.isnan(p) else abs(p - m) / (1 if sm == 0 else sm) for p, m, sm in zip(plus, minus, s)]
    ref = 100 * pine_rma(dx, 14)
    v = ta.adx(df["high"], df["low"], df["close"], 14, 14).to_numpy()
    m = ~np.isnan(ref)
    assert np.allclose(v[m], ref[m], atol=1e-9), np.nanmax(np.abs(v[m] - ref[m]))
    assert np.isnan(v[~m]).all()


def test_percentile_nearest_rank():
    s = pd.Series(np.arange(1, 101, dtype=float))
    v = ta.percentile_nearest_rank(s, 10, 20).to_numpy()
    # window [91..100], 20% of 10 -> rank 2 -> 92
    assert v[-1] == 92
    v = ta.percentile_nearest_rank(s, 10, 95).to_numpy()
    assert v[-1] == 100  # ceil(9.5)=10 -> 100


def test_barssince():
    cond = pd.Series([False, True, False, False, True, False])
    v = ta.barssince(cond).to_numpy()
    assert np.isnan(v[0]) and list(v[1:]) == [0, 1, 2, 0, 1]
