"""Does recent offensive snap share improve who-absorbs-the-targets for RB/WR backups?

Re-runs the 2024-25 starter-Out backtest across snap weights, with and without the depth-chart bonus, scored on a
fixed common sample.  Result (see README): RB corr(projection, actual) 0.21 -> 0.35 (snap only) / 0.29 -> 0.32-0.34
(with depth bonus); WR 0.09 -> 0.15, a real but small gain.  Shipped: RB 0.5, WR 0.25.
"""
import sys, copy, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np, pandas as pd
import backtest_backups as B
from props import config as C
orig_bonus=copy.deepcopy(C.DEPTH_BONUS); res=[]
for bonus_scale in (0.0, 1.0):                      # 1.0 = current production depth bonus
    for sw in (0.0, 0.1, 0.25, 0.5, 1.0):
        C.DEPTH_BONUS={k:{r:v*bonus_scale for r,v in d.items()} for k,d in orig_bonus.items()}
        C.SNAP_WEIGHT={"QB":0.0,"RB":sw,"WR":sw}
        df=pd.concat([B.run(2024),B.run(2025)],ignore_index=True); df["bonus"]=bonus_scale; df["sw"]=sw; res.append(df)
C.DEPTH_BONUS=orig_bonus
D=pd.concat(res); key=["season","week","cat","name"]
common=None
for _,g in D.groupby(["bonus","sw"]):
    k=g[key].drop_duplicates(); common=k if common is None else common.merge(k,on=key)
X=D.merge(common,on=key); X=X[X.act_vol>0]
rm=lambda e: float(np.sqrt(np.mean(np.asarray(e)**2)))
print(f"{'cat':3s} {'depthbonus':>10s} {'snapW':>6s} {'n':>4s} {'predUp':>7s} {'realUp':>7s} {'corr':>5s} {'volRMSE':>8s} {'naive':>6s} {'ydsRMSE':>8s}")
for cat in ("RB","WR"):
    for (bs,sw),g in X[X.cat==cat].groupby(["bonus","sw"]):
        up_p=g.proj_vol-g.base_vol; up_a=g.act_vol-g.base_vol
        print(f"{cat:3s} {bs:10.1f} {sw:6.2f} {len(g):4d} {up_p.mean():7.2f} {up_a.mean():7.2f} {np.corrcoef(g.proj_vol,g.act_vol)[0,1]:5.2f} {rm(g.proj_vol-g.act_vol):8.2f} {rm(g.base_vol-g.act_vol):6.2f} {rm(g.proj_yds-g.act_yds):8.1f}")
