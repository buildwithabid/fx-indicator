"""Gates A-F from spec/rules_v1.md, vectorised. Mirrors pine/core.pine 1:1.

build_features(m15) -> DataFrame with all indicator columns and gate booleans that do not depend
on state (A-E). Gate F (throttle / daily stop) is path-dependent and lives in engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ta
from .data import align_htf_last_closed, resample


@dataclass(frozen=True)
class Params:
    atr_sl_mult: float = 1.5
    tp_r: float = 2.0
    adx_min: float = 20.0
    # frozen (not tuned)
    ema_fast_4h: int = 50
    ema_slow_4h: int = 200
    adx_len: int = 14
    ema_pull: int = 20
    ema_struct: int = 50
    pull_window: int = 6
    rsi_len: int = 14
    rsi_veto: float = 70.0
    atr_len: int = 14
    atr_pct_window: int = 480
    atr_pct_lo: float = 20.0
    atr_pct_hi: float = 95.0
    spike_mult: float = 3.0
    spike_bars: int = 4
    swing_len: int = 10
    swing_buffer_atr: float = 0.1
    sessions: tuple = ((7 * 60 + 15, 10 * 60 + 45), (13 * 60 + 45, 16 * 60))  # [start, end) minutes UTC
    news_blackout: tuple = ((12 * 60 + 25, 13 * 60 + 5), (13 * 60 + 55, 14 * 60 + 20))
    friday_cutoff: int = 15 * 60
    monday_start: int = 7 * 60 + 15
    blackout_dates: frozenset = field(default_factory=frozenset)
    max_signals_day: int = 2
    min_bars_between: int = 8
    max_losses_day: int = 2
    max_day_r_loss: float = -2.0


def _in_windows(minute_of_day: pd.Series, windows) -> pd.Series:
    ok = pd.Series(False, index=minute_of_day.index)
    for a, b in windows:
        ok |= (minute_of_day >= a) & (minute_of_day < b)
    return ok


def session_ok(index: pd.DatetimeIndex, p: Params) -> pd.Series:
    mod = pd.Series(index.hour * 60 + index.minute, index=index)
    dow = pd.Series(index.dayofweek, index=index)  # Mon=0 .. Sun=6
    ok = _in_windows(mod, p.sessions)
    ok &= ~_in_windows(mod, p.news_blackout)
    ok &= ~((dow == 4) & (mod >= p.friday_cutoff))
    ok &= dow != 6
    ok &= ~((dow == 0) & (mod < p.monday_start))
    if p.blackout_dates:
        dates = pd.Series(index.strftime("%Y-%m-%d"), index=index)
        ok &= ~dates.isin(p.blackout_dates)
    return ok


def build_features(m15: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    df = m15.copy()
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]

    # --- 15m indicators
    df["ema20"] = ta.ema(c, p.ema_pull)
    df["ema50"] = ta.ema(c, p.ema_struct)
    df["rsi"] = ta.rsi(c, p.rsi_len)
    df["atr"] = ta.atr(h, l, c, p.atr_len)
    df["atr_p_lo"] = ta.percentile_nearest_rank(df["atr"], p.atr_pct_window, p.atr_pct_lo)
    df["atr_p_hi"] = ta.percentile_nearest_rank(df["atr"], p.atr_pct_window, p.atr_pct_hi)
    rng = h - l
    spike = rng > p.spike_mult * df["atr"].shift(1)
    df["spike_recent"] = spike.rolling(p.spike_bars, min_periods=1).max().astype(bool)
    df["swing_low"] = ta.lowest(l, p.swing_len)
    df["swing_high"] = ta.highest(h, p.swing_len)

    # --- HTF
    h4 = resample(df[["open", "high", "low", "close"]], "4h")
    h4["ema_fast"] = ta.ema(h4["close"], p.ema_fast_4h)
    h4["ema_slow"] = ta.ema(h4["close"], p.ema_slow_4h)
    a4 = align_htf_last_closed(df.index, h4, ["ema_fast", "ema_slow", "close"], "4h")
    df["h4_ema_fast"], df["h4_ema_slow"], df["h4_close"] = a4["ema_fast"], a4["ema_slow"], a4["close"]

    h1 = resample(df[["open", "high", "low", "close"]], "1h")
    h1["adx"] = ta.adx(h1["high"], h1["low"], h1["close"], p.adx_len, p.adx_len)
    a1 = align_htf_last_closed(df.index, h1, ["adx"], "1h")
    df["h1_adx"] = a1["adx"]

    # --- Gate A: 4H regime
    df["A_long"] = (df["h4_ema_fast"] > df["h4_ema_slow"]) & (df["h4_close"] > df["h4_ema_fast"])
    df["A_short"] = (df["h4_ema_fast"] < df["h4_ema_slow"]) & (df["h4_close"] < df["h4_ema_fast"])

    # --- Gate B: 1H strength (threshold applied in engine so grid can vary adx_min cheaply)
    # --- Gate C: pullback + confirmation
    w = p.pull_window
    touched_lo = l <= df["ema20"]
    touched_hi = h >= df["ema20"]
    df["C_pull_long"] = (ta.barssince(touched_lo) <= w - 1) & (c.rolling(w).min() > df["ema50"])
    df["C_pull_short"] = (ta.barssince(touched_hi) <= w - 1) & (c.rolling(w).max() < df["ema50"])
    body = (c - o).abs()
    good_range = rng > 0
    df["C_conf_long"] = (c > o) & (c > h.shift(1)) & (body >= 0.5 * rng) & good_range & (df["rsi"] < p.rsi_veto)
    df["C_conf_short"] = (c < o) & (c < l.shift(1)) & (body >= 0.5 * rng) & good_range & (df["rsi"] > 100 - p.rsi_veto)
    df["C_long"] = df["C_pull_long"] & df["C_conf_long"]
    df["C_short"] = df["C_pull_short"] & df["C_conf_short"]

    # --- Gate D: volatility
    df["D"] = (df["atr"] >= df["atr_p_lo"]) & (df["atr"] <= df["atr_p_hi"]) & ~df["spike_recent"]

    # --- Gate E: session
    df["E"] = session_ok(df.index, p)

    # --- Quality badge (display only)
    q = (df["rsi"].between(40, 60)).astype(int)
    q += ((body >= 0.7 * rng) & good_range).astype(int)
    q_long = q + ((c.rolling(w).min() - df["ema50"]) >= 0.25 * df["atr"]).astype(int)
    q_short = q + ((df["ema50"] - c.rolling(w).max()) >= 0.25 * df["atr"]).astype(int)
    df["Q_long"], df["Q_short"] = q_long, q_short

    # --- candidate (A, C, D, E; B applied in engine)
    df["cand_long"] = df["A_long"] & df["C_long"] & df["D"] & df["E"]
    df["cand_short"] = df["A_short"] & df["C_short"] & df["D"] & df["E"]
    return df
