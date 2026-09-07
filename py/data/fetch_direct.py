"""Rate-limited direct downloader for Dukascopy daily M1 candle files -> M15 CSV per pair-year.

URL: https://datafeed.dukascopy.com/datafeed/{PAIR}/{YYYY}/{MM-1:02d}/{DD:02d}/BID_candles_min_1.bi5
bi5 = LZMA (raw .lzma/xz alone format), records of 24 bytes big-endian:
  int32 secs-from-day-start, int32 open, int32 close, int32 low, int32 high, float32 volume
Prices are ints scaled by 1e5 (1e3 for JPY-quoted pairs). Times are UTC.
Raw files are cached in data/cache/<pair>/<yyyy-mm-dd>.bi5 (empty file = no data that day), so
re-runs are resumable. Output: data/raw/<pair>-m15-bid-<yyyy>-01-01-<yyyy+1>-01-01.csv
"""
from __future__ import annotations

import datetime as dt
import lzma
import os
import struct
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
RAW = os.path.join(HERE, "raw")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
MIN_GAP = float(os.environ.get("DUKA_GAP", "1.2"))  # seconds between requests

_last = 0.0


def get(url: str) -> bytes | None:
    """Returns bytes, b'' for 404/empty, raises after too many failures."""
    global _last
    backoff = 20
    for attempt in range(12):
        wait = MIN_GAP - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
            if e.code in (429, 503, 502):
                print(f"  {e.code} -> sleep {backoff}s", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 600)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"  net err {e} -> sleep {backoff}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)
    raise RuntimeError(f"giving up on {url}")


def decode(raw: bytes, scale: float):
    if not raw:
        return []
    data = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    n = len(data) // 24
    out = []
    for k in range(n):
        t, o, c, l, h, v = struct.unpack(">iiiiif", data[k * 24 : (k + 1) * 24])
        out.append((t, o / scale, h / scale, l / scale, c / scale))
    return out


def to_m15(day: dt.date, m1: list):
    """Aggregate M1 (secs, o, h, l, c) into M15 buckets; returns rows (epoch_ms, o, h, l, c)."""
    base = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    buckets = {}
    for t, o, h, l, c in m1:
        b = (t // 900) * 900
        if b not in buckets:
            buckets[b] = [o, h, l, c]
        else:
            x = buckets[b]
            x[1] = max(x[1], h)
            x[2] = min(x[2], l)
            x[3] = c
    return [((base + b) * 1000, *buckets[b]) for b in sorted(buckets)]


def fetch_year(pair: str, year: int, end: dt.date | None = None):
    scale = 1e3 if pair.endswith("JPY") else 1e5
    os.makedirs(os.path.join(CACHE, pair), exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    start = dt.date(year, 1, 1)
    stop = end or dt.date(year + 1, 1, 1)
    out_path = os.path.join(RAW, f"{pair.lower()}-m15-bid-{start}-{stop}.csv")
    if os.path.exists(out_path):
        print(f"skip {out_path}")
        return
    rows = []
    d = start
    n_new = 0
    while d < stop:
        cp = os.path.join(CACHE, pair, f"{d}.bi5")
        if os.path.exists(cp):
            raw = open(cp, "rb").read()
        else:
            if d.weekday() == 5:  # Saturday: market closed, skip request
                raw = b""
            else:
                url = f"https://datafeed.dukascopy.com/datafeed/{pair}/{d.year}/{d.month-1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
                raw = get(url)
                n_new += 1
            open(cp, "wb").write(raw)
        try:
            rows.extend(to_m15(d, decode(raw, scale)))
        except lzma.LZMAError:
            print(f"  bad lzma {pair} {d}, refetching once")
            os.remove(cp)
            raw = get(url)
            open(cp, "wb").write(raw)
            rows.extend(to_m15(d, decode(raw, scale)))
        if n_new and n_new % 50 == 0:
            print(f"  {pair} {d} ({len(rows)} bars)", flush=True)
        d += dt.timedelta(days=1)
    with open(out_path, "w") as f:
        f.write("timestamp,open,high,low,close\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.5f},{r[2]:.5f},{r[3]:.5f},{r[4]:.5f}\n")
    print(f"wrote {out_path} ({len(rows)} bars)", flush=True)


if __name__ == "__main__":
    pairs = sys.argv[1:] or ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
    for pair in pairs:
        for y in range(2019, 2027):
            fetch_year(pair, y, dt.date(2026, 9, 1) if y == 2026 else None)
