"""IS-only: (1) trailing chandelier exit instead of fixed TP; (2) same rules on 1H bars (swing-ish)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fx.data import PAIRS, load_m15, resample
from fx.rules import Params, build_features
from fx.engine import COSTS, pip_size
from fx.metrics import summary, fmt
from fx import indicators as ta

IS = ("2019-01-01", "2023-01-01")


def run_trail(f, pair, p, trail_mult=2.0, ema_exit=False):
    spread_pips, slip_pips = COSTS[pair]; ps = pip_size(pair); spread, slip = spread_pips*ps, slip_pips*ps
    idx = f.index; o,h,l,c = (f[k].to_numpy() for k in ("open","high","low","close"))
    atr = f["atr"].to_numpy(); swl=f["swing_low"].to_numpy(); swh=f["swing_high"].to_numpy(); adx=f["h1_adx"].to_numpy()
    cl=f["cand_long"].to_numpy(); cs=f["cand_short"].to_numpy(); ema=f["ema20"].to_numpy()
    days = idx.normalize().to_numpy(); n=len(f); trades=[]
    open_dir=pending=0; fill=sl=sl_dist=0.0; hh=ll=0.0; cur_day=None; day_sig=day_loss=0; day_r=0.0; stopped=False; last=-10**9
    for i in range(n):
        if days[i]!=cur_day: cur_day=days[i]; day_sig=day_loss=0; day_r=0.0; stopped=False
        if pending:
            open_dir=pending; pending=0; fill=o[i]+spread*open_dir; entry_i=i; hh=h[i]; ll=l[i]
        if open_dir:
            exited=False
            if open_dir>0:
                if l[i]<=sl: px=sl-slip; exited=True
                elif ema_exit and c[i]<ema[i] and i>entry_i: px=c[i]; exited=True
                hh=max(hh,h[i]); sl=max(sl, hh-trail_mult*atr[i])
            else:
                if h[i]>=sl: px=sl+slip; exited=True
                elif ema_exit and c[i]>ema[i] and i>entry_i: px=c[i]; exited=True
                ll=min(ll,l[i]); sl=min(sl, ll+trail_mult*atr[i])
            if exited:
                r=(px-fill)/sl_dist*open_dir; trades.append(dict(pair=pair,dir=open_dir,signal_time=idx[entry_i],r=r,bars=i-entry_i))
                day_r+=r
                if r<0: day_loss+=1
                if day_loss>=p.max_losses_day or day_r<=p.max_day_r_loss: stopped=True
                open_dir=0
        if open_dir or pending or stopped or day_sig>=p.max_signals_day or i-last<p.min_bars_between: continue
        if not adx[i]>p.adx_min or np.isnan(atr[i]) or np.isnan(swl[i]): continue
        if cl[i]: d=1; sl_dist=max(p.atr_sl_mult*atr[i], c[i]-swl[i]+0.1*atr[i])
        elif cs[i]: d=-1; sl_dist=max(p.atr_sl_mult*atr[i], swh[i]-c[i]+0.1*atr[i])
        else: continue
        if i+1>=n: break
        sl=c[i]-d*sl_dist; pending=d; last=i; day_sig+=1
    return pd.DataFrame(trades)


p = Params()
print("=== 15m, v1 entry, chandelier 2xATR trailing (no TP)")
allt=[]
for pair in PAIRS:
    f = build_features(load_m15(pair), p).loc[IS[0]:IS[1]]
    t = run_trail(f, pair, p, 2.0); allt.append(t); print(f"  {pair} {fmt(summary(t))}")
print("  ALL", fmt(summary(pd.concat(allt))))

print("=== 15m, v1 entry, exit on close back through EMA20 (or 1.5ATR stop)")
allt=[]
for pair in PAIRS:
    f = build_features(load_m15(pair), p).loc[IS[0]:IS[1]]
    t = run_trail(f, pair, p, 99.0, ema_exit=True); allt.append(t); print(f"  {pair} {fmt(summary(t))}")
print("  ALL", fmt(summary(pd.concat(allt))))

print("=== 1H bars, same rules (HTF = 4H/1D via same code path: '4h'->'1D'? no: use 4H regime + 1H ADX on 1H bars)")
from fx.engine import run
from fx.rules import session_ok
allt=[]
for pair in PAIRS:
    m = resample(load_m15(pair), "1h")
    f = build_features(m, p).loc[IS[0]:IS[1]]   # note: HTF resample of 1H to 4h/1h inside works the same
    # session gate on 1H bars: allow 07-16 UTC, weekdays
    mod = f.index.hour*60+f.index.minute
    f["E"] = (mod>=7*60)&(mod<16*60)&(f.index.dayofweek<5)&~((f.index.dayofweek==4)&(mod>=15*60))
    f["cand_long"]=f["A_long"]&f["C_long"]&f["D"]&f["E"]; f["cand_short"]=f["A_short"]&f["C_short"]&f["D"]&f["E"]
    pp = Params(max_signals_day=1, min_bars_between=4)
    t = run(f, pair, pp); allt.append(t); print(f"  {pair} {fmt(summary(t))}")
print("  ALL", fmt(summary(pd.concat(allt))))
