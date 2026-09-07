"""Load Dukascopy M15 CSVs and build UTC-anchored HTF frames."""
from __future__ import annotations

import glob
import os

import pandas as pd

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]


def load_m15(pair: str, raw_dir: str = RAW, tf: str = "m15") -> pd.DataFrame:
    if tf != "m15":
        raw_dir = raw_dir + "_" + tf
    files = sorted(glob.glob(os.path.join(raw_dir, f"{pair.lower()}-{tf}-bid-*.csv")))
    if not files:
        raise FileNotFoundError(f"no raw csv for {pair} in {raw_dir}")
    parts = [pd.read_csv(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"]).drop_duplicates("time").sort_values("time").set_index("time")
    df = df[["open", "high", "low", "close"]].astype(float)
    # Dukascopy pads weekends/holidays with flat zero-range bars when using cache; drop them.
    df = df[(df["high"] > df["low"])]
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """UTC-anchored OHLC resample; drops empty buckets. rule: '1h' or '4h'."""
    o = df["open"].resample(rule, label="left", closed="left").first()
    h = df["high"].resample(rule, label="left", closed="left").max()
    l = df["low"].resample(rule, label="left", closed="left").min()
    c = df["close"].resample(rule, label="left", closed="left").last()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return out


def align_htf_last_closed(m15_index: pd.DatetimeIndex, htf: pd.DataFrame, cols: list[str], rule: str) -> pd.DataFrame:
    """For each 15m bar, attach the values of the LAST CLOSED HTF bar.

    HTF bar opening at t (UTC-anchored) closes at t + rule. It is 'closed' for a 15m bar opening at
    time s iff t + rule <= s. Equivalent to Pine request.security(expr[1], lookahead_on) on
    UTC-aligned charts.
    """
    step = pd.Timedelta(rule)
    close_time = htf.index + step
    tmp = htf[cols].copy()
    tmp.index = close_time
    tmp = tmp[~tmp.index.duplicated(keep="last")]
    aligned = tmp.reindex(tmp.index.union(m15_index)).ffill().reindex(m15_index)
    return aligned
