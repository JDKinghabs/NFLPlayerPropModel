"""Is yards allowed per PLAY a better defense rating than yards allowed per GAME?

Result (see README): no.  Per-game is better for QB and WR (it captures how much opponents have to throw),
per-play has a ~zero or negative pass-through for WRs.  We keep per-game.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np, pandas as pd
import backtest_elite as BE
from props import config as C

def rate_factor(season, cat, k_def=6, lam=0.5):
    """Defense factor from yards allowed PER PLAY (attempt/carry/target) instead of per game."""
    def agg(df):
        d = df if cat.def_positions is None else df[df.position.isin(cat.def_positions)]
        return d.groupby(["opponent_team","week"]).agg(yd=(cat.yards,"sum"), vol=(cat.volume,"sum")).reset_index()
    a, pa = agg(BE.get(season)), agg(BE.get(season-1))
    prev_rate = pa.groupby("opponent_team").yd.sum()/pa.groupby("opponent_team").vol.sum(); lg=pa.yd.sum()/pa.vol.sum()
    out = {}
    for w in range(4,19):
        h=a[a.week<w].groupby("opponent_team").agg(yd=("yd","sum"),vol=("vol","sum"),g=("week","size"))
        if h.empty: continue
        cur=h.yd/h.vol; prior=lam*prev_rate.reindex(h.index).fillna(lg)+(1-lam)*lg
        bl=(h.g*cur+k_def*prior)/(h.g+k_def); out[w]=bl/bl.mean()
    return out

rows=[]
for k,cat in C.CATS.items():
    for s in (2022,2023,2024,2025):
        d=BE.run(s,cat,C.PLAYER_PRIOR_GAMES,C.DEF_PRIOR_GAMES,C.DEF_PRIOR_REGRESS); rf=rate_factor(s,cat)
        d["f_rate"]=[rf.get(w,pd.Series(dtype=float)).get(o,np.nan) for w,o in zip(d.week,d.opp)]
        d["cat"]=k; rows.append(d)
D=pd.concat(rows).dropna(subset=["f_rate"])
rm=lambda e: float(np.sqrt(np.mean(np.asarray(e)**2)))
print(f"{'':6s}{'n':>5s} {'corr(f_game,f_rate)':>20s} | RMSE at beta=0.75: {'per-game (current)':>20s} {'per-play':>10s} {'average':>9s} | best beta: per-game / per-play / avg")
for k in C.CATS:
    d=D[D.cat==k]; out=[]
    for name,col in (("game","f"),("play","f_rate")):
        pass
    def proj(f,beta,pull=C.ELITE_GROUP_PULL):
        gm=d.groupby(["season","week"]).base.transform("mean"); b=(1-pull)*d.base+pull*gm; return b*(1+beta*(f-1))
    f_avg=(d.f+d.f_rate)/2
    r={nm:rm(d.y-proj(f,0.75)) for nm,f in (("game",d.f),("play",d.f_rate),("avg",f_avg))}
    best={nm:min(((rm(d.y-proj(f,b)),b) for b in (0.25,0.5,0.75,1.0,1.25,1.5,2.0)))  for nm,f in (("game",d.f),("play",d.f_rate),("avg",f_avg))}
    none=rm(d.y-proj(d.f*0+1,0.0))
    print(f"{k:6s}{len(d):5d} {np.corrcoef(d.f,d.f_rate)[0,1]:20.2f} | {'':18s}{r['game']:10.1f} {r['play']:10.1f} {r['avg']:9.1f} | "
          f"{best['game'][0]:.1f}@{best['game'][1]} / {best['play'][0]:.1f}@{best['play'][1]} / {best['avg'][0]:.1f}@{best['avg'][1]}   (no matchup at all: {none:.1f})")
# how strongly does each factor explain outcomes? slope of (y/base-1) on (f-1)
print("\nPass-through slope of realised/baseline on each factor (1.0 = factor is exactly right):")
for k in C.CATS:
    d=D[D.cat==k]; y=d.y/d.base-1
    print(f"  {k}: per-game slope={np.polyfit(d.f-1,y,1)[0]:.2f}   per-play slope={np.polyfit(d.f_rate-1,y,1)[0]:.2f}   spread of factor (std): game={d.f.std():.3f} play={d.f_rate.std():.3f}")
