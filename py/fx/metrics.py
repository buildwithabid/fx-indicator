"""Performance metrics on a trades DataFrame (column r = R-multiple)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summary(t: pd.DataFrame, days: float | None = None) -> dict:
    n = len(t)
    if n == 0:
        return dict(trades=0, wr=np.nan, exp_r=np.nan, pf=np.nan, max_dd_r=np.nan, avg_win=np.nan, avg_loss=np.nan,
                    streak=0, per_day=np.nan)
    r = t["r"].to_numpy()
    wins = r[r > 0]
    losses = r[r <= 0]
    eq = np.cumsum(r)
    dd = eq - np.maximum.accumulate(np.concatenate([[0], eq]))[1:]
    # longest losing streak
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    return dict(
        trades=n,
        wr=len(wins) / n,
        exp_r=r.mean(),
        pf=(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf,
        max_dd_r=-dd.min(),
        avg_win=wins.mean() if len(wins) else 0.0,
        avg_loss=losses.mean() if len(losses) else 0.0,
        streak=best,
        per_day=(n / days) if days else np.nan,
        total_r=r.sum(),
    )


def fmt(s: dict) -> str:
    if s["trades"] == 0:
        return "no trades"
    return (f"n={s['trades']:4d}  WR={s['wr']*100:5.1f}%  exp={s['exp_r']:+.3f}R  PF={s['pf']:.2f}  "
            f"maxDD={s['max_dd_r']:.1f}R  totR={s['total_r']:+.1f}  streak={s['streak']}")


def table(t: pd.DataFrame, by: str, days_per_group: dict | None = None) -> pd.DataFrame:
    rows = []
    for k, g in t.groupby(by):
        s = summary(g, (days_per_group or {}).get(k))
        s[by] = k
        rows.append(s)
    return pd.DataFrame(rows).set_index(by)


def monte_carlo_dd(r: np.ndarray, n_iter: int = 1000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    dds = []
    for _ in range(n_iter):
        x = rng.permutation(r)
        eq = np.cumsum(x)
        dd = eq - np.maximum.accumulate(np.concatenate([[0], eq]))[1:]
        dds.append(-dd.min())
    dds = np.array(dds)
    return dict(dd_p50=np.percentile(dds, 50), dd_p95=np.percentile(dds, 95), dd_max=dds.max())


def session_label(ts: pd.Series) -> pd.Series:
    mod = ts.dt.hour * 60 + ts.dt.minute
    return pd.Series(np.where(mod < 12 * 60, "London", "NY"), index=ts.index)
