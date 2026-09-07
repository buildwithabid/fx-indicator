"""IS-only research of the ICT/SMC model. Engine supports limit entry at the OB with validity window and
TP1/TP2/TP3 scale-out (1/3 each) with stop to breakeven after TP1.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fx.data import PAIRS, load_m15
from fx.rules import Params, build_features
from fx.smc import add_smc, htf_bias
from fx.engine import COSTS, pip_size
from fx.metrics import summary, fmt

IS = ("2019-01-01", "2023-01-01")


def run_smc(f, pair, p, tps=(1.0, 2.0, 3.0), be_after_tp1=True, ob_valid=12, entry="ob_top", sl_buf=0.1, min_sl_atr=0.8, max_sl_atr=3.0):
    spread_pips, slip_pips = COSTS[pair]; ps = pip_size(pair); spread, slip = spread_pips * ps, slip_pips * ps
    idx = f.index; o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr = f["atr"].to_numpy(); cl = f["cand_long"].to_numpy(); cs = f["cand_short"].to_numpy()
    top = f["ob_top"].to_numpy(); bot = f["ob_bot"].to_numpy()
    days = idx.normalize().to_numpy(); n = len(f); trades = []
    open_dir = 0; pend = 0; pend_until = -1; lvl = sl0 = sl = fill = sl_dist = 0.0; sig_time = None
    parts_left = 0; r_acc = 0.0; entry_i = 0
    cur_day = None; day_sig = day_loss = 0; day_r = 0.0; stopped = False; last = -10**9
    for i in range(n):
        if days[i] != cur_day:
            cur_day = days[i]; day_sig = day_loss = 0; day_r = 0.0; stopped = False
        if pend != 0:
            d = pend
            if (d > 0 and l[i] <= lvl) or (d < 0 and h[i] >= lvl):
                px = min(o[i], lvl) if d > 0 else max(o[i], lvl)
                fill = px + spread * d; open_dir = d; pend = 0; entry_i = i
                sl = sl0; parts_left = len(tps); r_acc = 0.0
                tp_levels = [fill + d * k * sl_dist for k in tps]
            elif i >= pend_until or (d > 0 and c[i] < bot_lvl) or (d < 0 and c[i] > bot_lvl):
                pend = 0
        if open_dir != 0:
            d = open_dir
            hit_sl = (l[i] <= sl) if d > 0 else (h[i] >= sl)
            if hit_sl:
                px = sl - slip * d
                r_part = (px - fill) / sl_dist * d * (parts_left / len(tps))
                r_acc += r_part; parts_left = 0
            else:
                k = len(tps) - parts_left
                while parts_left > 0 and ((d > 0 and h[i] >= tp_levels[k]) or (d < 0 and l[i] <= tp_levels[k])):
                    r_acc += (tp_levels[k] - fill) / sl_dist * d / len(tps); parts_left -= 1; k += 1
                    if be_after_tp1 and parts_left > 0:
                        sl = fill
            if parts_left == 0:
                trades.append(dict(pair=pair, dir=d, signal_time=sig_time, entry_time=idx[entry_i], exit_time=idx[i], r=r_acc, bars=i - entry_i, sl_dist=sl_dist))
                day_r += r_acc
                if r_acc < 0: day_loss += 1
                if day_loss >= p.max_losses_day or day_r <= p.max_day_r_loss: stopped = True
                open_dir = 0
        if open_dir or pend or stopped or day_sig >= p.max_signals_day or i - last < p.min_bars_between: continue
        if np.isnan(atr[i]): continue
        if cl[i]:
            d = 1; lvl = top[i] if entry == "ob_top" else (top[i] + bot[i]) / 2; sl0 = bot[i] - sl_buf * atr[i]; bot_lvl = bot[i]
        elif cs[i]:
            d = -1; lvl = bot[i] if entry == "ob_top" else (top[i] + bot[i]) / 2; sl0 = top[i] + sl_buf * atr[i]; bot_lvl = top[i]
        else:
            continue
        sl_dist = abs(lvl - sl0)
        if sl_dist < min_sl_atr * atr[i]:
            sl0 = lvl - d * min_sl_atr * atr[i]; sl_dist = min_sl_atr * atr[i]
        if sl_dist > max_sl_atr * atr[i]: continue
        if (d > 0 and c[i] <= lvl) or (d < 0 and c[i] >= lvl): continue  # already inside/below zone
        pend = d; pend_until = i + ob_valid; sig_time = idx[i]; last = i; day_sig += 1
    return pd.DataFrame(trades)


def build(pair, lo=IS[0], hi=IS[1], n15=3, disp=1.0, tf="m15"):
    m = load_m15(pair, tf=tf)
    f = build_features(m, Params())
    f = add_smc(f, n=n15, disp_atr=disp)
    f["bias_1h"] = htf_bias(m, "1h", 3); f["bias_4h"] = htf_bias(m, "4h", 3); f["bias_d"] = htf_bias(m, "1D", 2)
    return f.loc[lo:hi]


def variants(f):
    E = f["E"]; D = f["D"]
    b_all_l = (f.bias_1h == 1) & (f.bias_4h == 1) & (f.bias_d == 1); b_all_s = (f.bias_1h == -1) & (f.bias_4h == -1) & (f.bias_d == -1)
    b_4h1h_l = (f.bias_1h == 1) & (f.bias_4h == 1); b_4h1h_s = (f.bias_1h == -1) & (f.bias_4h == -1)
    return {
        "S1 sweep+displacement->OB limit, bias 4H+1H, sessions": (f.setup_long & b_4h1h_l & E & D, f.setup_short & b_4h1h_s & E & D),
        "S2 same, bias D+4H+1H": (f.setup_long & b_all_l & E & D, f.setup_short & b_all_s & E & D),
        "S3 same, no HTF bias (15m structure only)": (f.setup_long & (f.s_trend == 1) & E & D, f.setup_short & (f.s_trend == -1) & E & D),
        "S4 displacement->OB without sweep, bias D+4H+1H": (f.disp_up & ~f.ob_top_any.isna() & b_all_l & E & D, f.disp_dn & ~f.ob_top_any.isna() & b_all_s & E & D),
        "S5 S1 without session filter": (f.setup_long & b_4h1h_l & D, f.setup_short & b_4h1h_s & D),
    }


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "m15"
    entry = sys.argv[2] if len(sys.argv) > 2 else "ob_top"
    print(f"### timeframe {tf}, entry {entry}")
    p = Params()
    feats = {pair: build(pair, tf=tf) for pair in PAIRS}
    # S4 needs OB for all displacement bars: recompute ob for disp bars lacking sweep -> approximate by reusing setup columns only where present
    names = list(variants(next(iter(feats.values()))).keys())
    for name in names:
        rows = []
        for pair in PAIRS:
            f = feats[pair]; cl, cs = variants(f)[name]
            g = f.copy(); g["cand_long"] = cl.fillna(False); g["cand_short"] = cs.fillna(False)
            if name.startswith("S4"):
                g["ob_top"] = g["ob_top_any"]; g["ob_bot"] = g["ob_bot_any"]
            for exit_name, kw in (("TP1/2/3 scale-out, BE after TP1", dict(tps=(1.0, 2.0, 3.0), be_after_tp1=True)),
                                  ("single TP 2R", dict(tps=(2.0,), be_after_tp1=False))):
                t = run_smc(g, pair, p, entry=entry, **kw); t["exit"] = exit_name; rows.append(t)
        t = pd.concat(rows, ignore_index=True)
        print(name)
        for exit_name, g in t.groupby("exit"):
            print(f"   {exit_name:32s} IS ALL {fmt(summary(g))}")
            print("      per pair:", "  ".join(f"{pp}:{summary(gg)['exp_r']:+.2f}R/{summary(gg)['trades']}" for pp, gg in g.groupby("pair")))
