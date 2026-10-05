"""Do two forward-looking facts known before kickoff add information beyond Sheet 1 projection?

  T1  teammates ruled Out/Doubtful (volume that gets vacated)
  T2  opposing defenders ruled Out/Doubtful (snap-weighted)

Result (see README): T2 shows nothing (t <= 0.6).  T1 points the right way but is not significant (QB t=1.4, RB 1.7 on only
38 games, WR 1.0); adding both does not improve leave-one-season-out accuracy.  Not shipped.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np, pandas as pd
import backtest_elite as BE
from props import config as C
from props.data import cached
rm=lambda e: float(np.sqrt(np.mean(np.asarray(e)**2)))
OUT=("Out","Doubtful")
def inj(y): 
    d=pd.read_csv(cached(f"injuries/injuries_{y}.csv", False)); d=d[d.game_type=="REG"]; return d[d.report_status.isin(OUT)]
def ols_t(x,y):
    X=np.column_stack([np.ones(len(x)),x]); b=np.linalg.lstsq(X,y,rcond=None)[0]; res=y-X@b
    se=np.sqrt(res.var(ddof=2)/((x-x.mean())**2).sum()); return b[1],b[1]/se

rows=[]
for k,cat in C.CATS.items():
    for s in (2023,2024,2025):
        d=BE.run(s,cat,C.PLAYER_PRIOR_GAMES,C.DEF_PRIOR_GAMES,C.DEF_PRIOR_REGRESS,topn=cat.elite_n)
        d["proj"]=BE.add_projection(d,C.ELITE_GROUP_PULL,None,k); d["ck"]=k; rows.append(d)
D=pd.concat(rows); D["r"]=D.y/D.proj-1

# ---------- T1: teammate absence ----------
stats={s:BE.get(s) for s in (2023,2024,2025)}; injs={s:inj(s) for s in (2023,2024,2025)}
def teammate_vacated(r):
    st=stats[r.season]; st=st[(st.team==r.team)&(st.week<r.week)]
    absent=set(injs[r.season].query("team==@r.team and week==@r.week").gsis_id)-{r.pid}
    if not absent: return 0.0
    col={"QB":"targets","WR":"targets","RB":"carries"}[r.ck]          # QB: how much of the passing target pool is gone
    tot=st[col].sum()
    if tot<=0: return 0.0
    if r.ck=="RB": st=st[st.position.isin(["RB","FB"])]; tot=st[col].sum() if st[col].sum()>0 else 1
    return float(st[st.player_id.isin(absent)][col].sum()/tot)
D["vac"]=D.apply(teammate_vacated,axis=1)
D["x1"]=D.vac/(1-D.vac.clip(upper=0.7))
print("== T1: teammates ruled Out/Doubtful -> does the elite player beat Sheet 1's projection? ==")
for k in C.CATS:
    d=D[D.ck==k]; has=d[d.vac>0.05]
    b,t=ols_t(d.x1.values,d.r.values)
    print(f"  {k}: n={len(d)}; {len(has)} games ({len(has)/len(d):.0%}) with >5% of volume vacated; slope of (actual/proj-1) on expected uplift = {b:+.2f} (t={t:+.1f}); "
          f"avg actual/proj-1 when vacated>5%: {has.r.mean():+.3f} vs else {d[d.vac<=0.05].r.mean():+.3f}")

# ---------- T2: opposing defense missing starters ----------
sn={}; 
for s in (2023,2024,2025):
    snap=pd.read_csv(cached(f"snap_counts/snap_counts_{s}.csv", False)); ro=pd.read_csv(cached(f"rosters/roster_{s}.csv", False),usecols=["gsis_id","pfr_id"]).dropna().drop_duplicates("pfr_id")
    snap=snap[(snap.game_type=="REG")&(snap.defense_snaps>0)].merge(ro,left_on="pfr_player_id",right_on="pfr_id")
    sn[s]=snap[["gsis_id","team","week","defense_pct"]]
inj_def={s:pd.read_csv(cached(f"injuries/injuries_{s}.csv", False)) for s in (2023,2024,2025)}
PASS_POS={"CB","S","DB","FS","SS","NB","DE","OLB","EDGE"}; RUN_POS={"DT","NT","DL","DE","LB","ILB","MLB","OLB"}
def def_missing(r):
    i=inj_def[r.season]; i=i[(i.team==r.opp)&(i.week==r.week)&(i.report_status.isin(OUT))]
    pos=PASS_POS if r.ck in("QB","WR") else RUN_POS
    i=i[i.position.isin(pos)]
    if i.empty: return 0.0
    h=sn[r.season]; h=h[(h.team==r.opp)&(h.week<r.week)]
    recent=h.sort_values("week").groupby("gsis_id").defense_pct.apply(lambda x: x.tail(3).mean())
    return float(recent.reindex(i.gsis_id).fillna(0).sum())          # sum of snap-share of absent defenders (1.0 = one full-time starter)
D["dm"]=D.apply(def_missing,axis=1)
print("\n== T2: opposing defenders ruled Out/Doubtful (snap-weighted) -> does the elite player beat Sheet 1's projection? ==")
for k in C.CATS:
    d=D[D.ck==k]; b,t=ols_t(d.dm.values,d.r.values); has=d[d.dm>=0.5]
    print(f"  {k}: n={len(d)}; {len(has)} games ({len(has)/len(d):.0%}) with >=0.5 starter-equivalents out; slope per starter-equivalent = {b:+.3f} (t={t:+.1f}); "
          f"avg actual/proj-1: {has.r.mean():+.3f} when >=0.5 out vs {d[d.dm<0.5].r.mean():+.3f} otherwise")
# incremental accuracy of using both, leave-one-season-out
print("\n== Accuracy if both are added (leave-one-season-out, level + 2 slopes) ==")
for k in C.CATS:
    d=D[D.ck==k]; e0=[];e1=[]
    for s in (2023,2024,2025):
        tr,te=d[d.season!=s],d[d.season==s]; X=np.column_stack([np.ones(len(tr)),tr.x1,tr.dm]); b=np.linalg.lstsq(X,tr.r.values,rcond=None)[0]
        p1=te.proj*(1+np.column_stack([np.ones(len(te)),te.x1,te.dm])@b); e0+=list(te.y-te.proj); e1+=list(te.y-p1)
    print(f"  {k}: RMSE {rm(e0):.1f} -> {rm(e1):.1f} ({(rm(e1)/rm(e0)-1)*100:+.1f}%)")
