"""Pine <-> Python parity check.

Usage:
  1. On TradingView, add dist/strategy.pine to FX:EURUSD 15m. Strategy Tester -> List of Trades -> Export (CSV).
  2. Chart menu -> Export chart data (CSV) for the same period (gives the exact bars Pine saw).
  3. python py/parity.py EURUSD trades.csv chart.csv

Compares signal timestamps (entry bar open time) between the TradingView trade list and the Python engine
run on the exported chart bars. Reports match %, and lists mismatches for investigation.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from fx.rules import Params, build_features
from fx.engine import run


def load_tv_chart(path):
    df = pd.read_csv(path)
    tcol = [c for c in df.columns if c.lower() in ("time", "timestamp")][0]
    t = pd.to_datetime(df[tcol], unit="s", utc=True) if pd.api.types.is_numeric_dtype(df[tcol]) else pd.to_datetime(df[tcol], utc=True)
    out = df.rename(columns=str.lower)[["open", "high", "low", "close"]].astype(float)
    out.index = t
    return out.sort_index()


def load_tv_trades(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    ent = df[df["Type"].str.contains("Entry", case=False, na=False)]
    tcol = [c for c in df.columns if "Date" in c or "time" in c.lower()][0]
    return pd.to_datetime(ent[tcol], utc=True).sort_values().reset_index(drop=True)


if __name__ == "__main__":
    pair, trades_csv, chart_csv = sys.argv[1], sys.argv[2], sys.argv[3]
    bars = load_tv_chart(chart_csv)
    feat = build_features(bars, Params())
    py = run(feat, pair, Params())
    py_entries = pd.Series(py["entry_time"]).sort_values().reset_index(drop=True)
    tv_entries = load_tv_trades(trades_csv)
    tv_entries = tv_entries[tv_entries >= bars.index[0] + pd.Timedelta(days=15)]  # skip warm-up
    py_entries = py_entries[py_entries >= bars.index[0] + pd.Timedelta(days=15)]
    tv_set, py_set = set(tv_entries), set(py_entries)
    both = tv_set & py_set
    print(f"TradingView entries: {len(tv_set)}   Python entries: {len(py_set)}   matched: {len(both)}")
    print(f"match rate (of TradingView): {100*len(both)/max(1,len(tv_set)):.1f}%")
    print("only in TradingView:", sorted(tv_set - py_set)[:20])
    print("only in Python:", sorted(py_set - tv_set)[:20])
