"""Would a second, independent method (volume x regressed efficiency) cross-check Sheet 1?

Result (see README): no.  It correlates 0.97-0.99 with the production projection, matches its accuracy, adds no
significant information (t = 0.9-1.6) and disagreement does not predict larger errors.  A second method built from the
same player history is a near-clone, so it is not shipped.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np, pandas as pd
import backtest_elite as BE
from props import config as C
from props.defense import shrink
rm=lambda e: float(np.sqrt(np.mean(np.asarray(e)**2)))

def opportunity_model(season, cat, rows, M_EFF, K_VOL=6):
    """Second method: project volume and efficiency separately. Uses only games before each target week."""
    cur, prev = BE.get(season), BE.get(season-1)
    pos = lambda d: d[d.position.isin(cat.positions) & (d[cat.volume].fillna(0) > 0)]
    c, p = pos(cur), pos(prev)
    c_by = {k: g.sort_values("week") for k, g in c.groupby("player_id")}
    pr = p.groupby("player_id").agg(g=("week","size"), vol=(cat.volume,"sum"), yds=(cat.yards,"sum"))
    lg_eff = p[cat.yards].sum()/p[cat.volume].sum()
    out=[]
    for pid, w in zip(rows.pid, rows.week):
        h = c_by[pid][c_by[pid].week < w]; n=len(h)
        vol_cur, vsum, ysum = h[cat.volume].mean(), h[cat.volume].sum(), h[cat.yards].sum()
        if pid in pr.index and pr.loc[pid,"g"]>=6:
            vol_pri = pr.loc[pid,"vol"]/pr.loc[pid,"g"]; eff_pri = shrink(pr.loc[pid,"yds"]/pr.loc[pid,"vol"], pr.loc[pid,"vol"], lg_eff, M_EFF)
        else: vol_pri, eff_pri = np.nan, lg_eff
        vol = shrink(vol_cur, n, vol_pri, K_VOL)
        eff = shrink(ysum/vsum, vsum, eff_pri, M_EFF)
        out.append(vol*eff)
    return np.array(out)

for k,cat in C.CATS.items():
    best=None
    for M in ({"QB":(100,200,400),"RB":(75,150,300),"WR":(40,80,160)}[k]):
        parts=[]
        for s in (2022,2023,2024,2025):
            d=BE.run(s,cat,C.PLAYER_PRIOR_GAMES,C.DEF_PRIOR_GAMES,C.DEF_PRIOR_REGRESS,topn=cat.elite_n)
            d["proj"]=BE.add_projection(d,C.ELITE_GROUP_PULL,None,k)
            d["m2_raw"]=opportunity_model(s,cat,d,M)
            # put M2 on the same footing as production: same winner's-curse pull + matchup + script, so the ONLY difference is the baseline method
            gm=d.groupby(["season","week"]).m2_raw.transform("mean"); base2=(1-C.ELITE_GROUP_PULL)*d.m2_raw+C.ELITE_GROUP_PULL*gm
            ratio=d.proj/ (((1-C.ELITE_GROUP_PULL)*d.base + C.ELITE_GROUP_PULL*d.groupby(["season","week"]).base.transform("mean")))   # production's matchup*script multiplier
            d["m2"]=base2*ratio; parts.append(d)
        D=pd.concat(parts)
        r=(rm(D.y-D.proj), rm(D.y-D.m2), rm(D.y-(D.proj+D.m2)/2), np.corrcoef(D.proj,D.m2)[0,1])
        if best is None or r[1]<best[1][1]: best=(M,r,D)
    M,r,D=best
    inc=np.polyfit(D.m2/D.proj-1, D.y/D.proj-1, 1); x=(D.m2/D.proj-1).values; yv=(D.y/D.proj-1).values
    res=yv-np.polyval(inc,x); se=res.std(ddof=2)/np.sqrt(((x-x.mean())**2).sum())
    dis=np.abs(D.m2/D.proj-1); err=np.abs(D.y/D.proj-1)
    print(f"\n{k} (n={len(D)}, best efficiency-shrink m={M})")
    print(f"  RMSE  production {r[0]:.1f} | opportunity model {r[1]:.1f} | 50/50 blend {r[2]:.1f}   | corr(production, opportunity) = {r[3]:.2f}")
    print(f"  does the 2nd method add information?  slope of (actual/prod-1) on (opp/prod-1) = {inc[0]:.2f} (se {se:.2f}, t={inc[0]/se:.1f})")
    q=pd.qcut(dis,3,labels=["methods agree","middle","methods disagree"])
    print("  avg |actual/prod - 1| by agreement tercile:", {str(g):round(float(err[q==g].mean()),3) for g in q.cat.categories}, "| corr(disagreement, error)=%.2f"%np.corrcoef(dis,err)[0,1])
