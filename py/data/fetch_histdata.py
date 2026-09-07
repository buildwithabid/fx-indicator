"""Download M1 forex history from histdata.com (free) and write M15 UTC CSVs into data/raw/.

histdata.com timestamps are EST without daylight saving (UTC-5 all year) -> add 5h for UTC.
Prices are bid quotes. Output format matches the Dukascopy loader: timestamp(ms UTC),open,high,low,close
Full years are one zip each; the current year is one zip per month.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import sys
import zipfile

import pandas as pd
from histdata import download_hist_data as dl
from histdata.api import Platform, TimeFrame

HERE = os.path.dirname(os.path.abspath(__file__))
ZIPS = os.path.join(HERE, "zips")
RAW = os.path.join(HERE, "raw")
TODAY = dt.date.today()


def fetch_zip(pair: str, year: int, month: int | None) -> str:
    os.makedirs(ZIPS, exist_ok=True)
    name = f"DAT_ASCII_{pair}_M1_{year}{month:02d}.zip" if month else f"DAT_ASCII_{pair}_M1_{year}.zip"
    path = os.path.join(ZIPS, name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    cwd = os.getcwd()
    os.chdir(ZIPS)
    try:
        out = dl(year=str(year), month=str(month) if month else None, pair=pair.lower(),
                 platform=Platform.GENERIC_ASCII, time_frame=TimeFrame.ONE_MINUTE)
    finally:
        os.chdir(cwd)
    got = os.path.join(ZIPS, os.path.basename(out))
    if got != path:
        os.replace(got, path)
    return path


def read_m1(path: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith(".csv")][0]
        raw = z.read(name)
    df = pd.read_csv(io.BytesIO(raw), sep=";", header=None, names=["t", "open", "high", "low", "close", "vol"])
    t = pd.to_datetime(df["t"], format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)
    df.index = t.dt.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].astype(float)


def to_m15(m1: pd.DataFrame) -> pd.DataFrame:
    o = m1["open"].resample("15min", label="left", closed="left").first()
    h = m1["high"].resample("15min", label="left", closed="left").max()
    l = m1["low"].resample("15min", label="left", closed="left").min()
    c = m1["close"].resample("15min", label="left", closed="left").last()
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()


def fetch_year(pair: str, year: int):
    os.makedirs(RAW, exist_ok=True)
    stop = dt.date(year + 1, 1, 1) if year < TODAY.year else dt.date(TODAY.year, TODAY.month, 1)
    out = os.path.join(RAW, f"{pair.lower()}-m15-bid-{year}-01-01-{stop}.csv")
    if os.path.exists(out):
        print("skip", os.path.basename(out))
        return
    if year < TODAY.year:
        parts = [read_m1(fetch_zip(pair, year, None))]
    else:
        parts = [read_m1(fetch_zip(pair, year, m)) for m in range(1, TODAY.month)]
    m1 = pd.concat(parts).sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    m15 = to_m15(m1)
    m15 = m15[m15.index < pd.Timestamp(stop, tz="UTC")]
    dec = 3 if pair.endswith("JPY") else 5
    with open(out, "w") as f:
        f.write("timestamp,open,high,low,close\n")
        for ts, r in zip(m15.index.as_unit("ms").asi8, m15.itertuples(index=False)):
            f.write(f"{ts},{r.open:.{dec}f},{r.high:.{dec}f},{r.low:.{dec}f},{r.close:.{dec}f}\n")
    print(f"wrote {os.path.basename(out)}  m1={len(m1)} m15={len(m15)}", flush=True)


if __name__ == "__main__":
    pairs = sys.argv[1:] or ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
    for pair in pairs:
        for y in range(2019, TODAY.year + 1):
            fetch_year(pair, y)
