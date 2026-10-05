"""Can we forecast how many touches an elite player gets, and do weak defenses / teammate absences move it?

Touches = QB pass attempts, RB carries + catches, WR targets.  Walk-forward 2023-25 on the Sheet 1 pools.

Result (see README): touches are steadier than yards (baseline misses 26% / 33% / 41% of the mean vs ~30% / 52% / 57% for yards).
 - QB: a defense's VOLUME-allowed rating predicts attempts (t = 4.1); adding it cuts attempt error 2.9% out of sample.
 - RB / WR: teammates ruled Out raise touches on average (RB +19% over 36 games, t = 3.6; WR +6%, t = 2.8) but the effect
   is rare and noisy, so it does not improve out-of-sample accuracy (+0.8%).
 - None of it improves the YARDS forecast.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import numpy as np, pandas as pd
import backtest_elite as BE
from props import config as C
from props.data import cached, STAT_COLS
from props.defense import shrink
rm=lambda e: float(np.sqrt(np.mean(np.asarray(e)**2)))
OUT=("Out","Doubtful")
SEAS=(2023,2024,2025)
def load(s):
    d=pd.read_csv(cached(f"stats_player/stats_player_week_{s}.csv", False), usecols=lambda c: c in STAT_COLS+["receptions"])
    d=d[d.season_type=="REG"].copy(); d["receptions"]=d.receptions.fillna(0)
    d["touch"]={"QB":d.attempts,"RB":d.carries+d.receptions,"WR":d.targets}["QB"]   # placeholder, set per cat below
    return d
S_={s:load(s) for s in SEAS+(2022,)}
def vol(d,k): return {"QB":d.attempts.fillna(0),"RB":(d.carries.fillna(0)+d.receptions),"WR":d.targets.fillna(0)}[k]
injs={s:(lambda x:x[(x.game_type=="REG")&x.report_status.isin(OUT)])(pd.read_csv(cached(f"injuries/injuries_{s}.csv", False))) for s in SEAS}

def vol_factor(s,k,cat,k_def=6,lam=0.5):
    """Defense factor for VOLUME faced (attempts/touches/targets allowed per game to the position group)."""
    def agg(df):
        d=df if cat.def_positions is None else df[df.position.isin(cat.def_positions)]
        d=d.assign(v=vol(d,k)); return d.groupby(["opponent_team","week"]).v.sum().reset_index()
    a,pa=agg(S_[s]),agg(S_[s-1]); prev=pa.groupby("opponent_team").v.mean(); lg=prev.mean(); out={}
    for w in range(4,19):
        h=a[a.week<w].groupby("opponent_team").v.agg(["mean","size"])
        if h.empty: continue
        pri=lam*prev.reindex(h.index).fillna(lg)+(1-lam)*lg
        bl=(h["size"]*h["mean"]+k_def*pri)/(h["size"]+k_def); out[w]=bl/bl.mean()
    return out

def build(k,cat):
    rows=[]
    for s in SEAS:
        d=BE.run(s,cat,C.PLAYER_PRIOR_GAMES,C.DEF_PRIOR_GAMES,C.DEF_PRIOR_REGRESS,topn=cat.elite_n); d["k"]=k; d["proj"]=BE.add_projection(d,C.ELITE_GROUP_PULL,None,k)
        cur,prev=S_[s],S_[s-1]; cur=cur.assign(v=vol(cur,k)); prev=prev.assign(v=vol(prev,k))
        elig=lambda x: x[x.position.isin(cat.positions)&(x[cat.volume].fillna(0)>0)]
        c,p=elig(cur),elig(prev); c_by={a:g.sort_values("week") for a,g in c.groupby("player_id")}
        pr=p.groupby("player_id").agg(g=("week","size"),v=("v","mean"))
        act=cur.set_index(["player_id","week"]).v
        vf=vol_factor(s,k,cat)
        bv,av,vac,fvv=[],[],[],[]
        for pid,w,team in zip(d.pid,d.week,d.team):
            h=c_by[pid][c_by[pid].week<w]; vp=pr.loc[pid,"v"] if (pid in pr.index and pr.loc[pid,"g"]>=6) else np.nan
            bv.append(shrink(h.v.mean(),len(h),vp,C.PLAYER_PRIOR_GAMES)); av.append(act.get((pid,w),np.nan))
            # teammates out: share of the relevant volume held by teammates ruled Out/Doubtful that week
            st=cur[(cur.team==team)&(cur.week<w)]; absent=set(injs[s].query("team==@team and week==@w").gsis_id)-{pid}
            col=st if k!="RB" else st[st.position.isin(["RB","FB"])]
            tot=col.v.sum() if k!="QB" else st.targets.fillna(0).sum()
            sh=(col[col.player_id.isin(absent)].v.sum()/tot if k!="QB" else st[st.player_id.isin(absent)].targets.fillna(0).sum()/tot) if tot>0 and absent else 0.0
            vac.append(float(sh))
            fvv.append(vf.get(w,pd.Series(dtype=float)).get(d.loc[d.pid==pid].opp.iloc[0] if False else None,np.nan))
        d["base_v"]=bv; d["act_v"]=av; d["vac"]=vac
        d["fv"]=[vf.get(w,pd.Series(dtype=float)).get(o,np.nan) for w,o in zip(d.week,d.opp)]
        rows.append(d)
    D=pd.concat(rows).merge(BE.game_lines(),on=["season","week","team"],how="left")
    D["x_vac"]=D.vac/(1-D.vac.clip(upper=0.7)); D["fy"]=D.f-1; D["fvol"]=D.fv-1
    D["fav7"]=(-D.spread)/7; D["tt_r"]=(D.ou/2+(-D.spread)/2)/22.0-1; D["home"]=D.home.astype(float)
    D["r"]=D.act_v/D.base_v-1
    return D.dropna(subset=["r","base_v","fv","tt_r"])

def ols(X,y):
    X1=np.column_stack([np.ones(len(X)),X]); b=np.linalg.lstsq(X1,y,rcond=None)[0]; res=y-X1@b
    cov=np.linalg.inv(X1.T@X1)*res.var(ddof=X1.shape[1]); return b[1:],b[1:]/np.sqrt(np.diag(cov)[1:])

LABEL={"QB":"pass attempts","RB":"touches (carries + catches)","WR":"targets"}
for k,cat in C.CATS.items():
    D=build(k,cat); y=D.r.values
    print(f"\n=== {k}: {LABEL[k]}  (n={len(D)}; baseline = shrunk season average; typical miss of baseline = {rm(D.act_v-D.base_v):.1f}, {rm(D.act_v-D.base_v)/D.act_v.mean():.0%} of mean)")
    for name,cols in (("teammates out (workload)",["x_vac"]),("weak D by yards allowed (our rating)",["fy"]),("weak D by VOLUME allowed",["fvol"]),
                      ("game script: favourite margin",["fav7"]),("game script: implied team total",["tt_r"]),("home",["home"])):
        b,t=ols(D[cols].values,y); print(f"   {name:38s} slope {b[0]:+.3f}  t={t[0]:+.1f}")
    cols=["x_vac","fvol","fav7"]; b,t=ols(D[cols].values,y)
    print("   joint [teammates out, volume-allowed D, favourite margin]: "+", ".join(f"{c}={bb:+.3f}(t={tt:+.1f})" for c,bb,tt in zip(cols,b,t)))
    e0=[];e1=[]
    for s in SEAS:                       # leave-one-season-out accuracy of the volume forecast
        tr,te=D[D.season!=s],D[D.season==s]; X1=np.column_stack([np.ones(len(tr)),tr[cols].values]); bb=np.linalg.lstsq(X1,tr.r.values,rcond=None)[0]
        e0+=list(te.act_v-te.base_v); e1+=list(te.act_v-te.base_v*(1+np.column_stack([np.ones(len(te)),te[cols].values])@bb))
    print(f"   volume forecast error (leave-one-season-out): baseline {rm(e0):.2f} -> with signals {rm(e1):.2f} ({(rm(e1)/rm(e0)-1)*100:+.1f}%)")
    has=D[D.vac>0.05]; print(f"   games with >5% of the volume vacated: {len(has)} ({len(has)/len(D):.0%}); actual/baseline-1 there: {has.r.mean():+.3f} vs {D[D.vac<=0.05].r.mean():+.3f} otherwise")

FOCUS={"QB":["fvol"],"RB":["x_vac"],"WR":["x_vac"]}
print("FOCUSED signals only (one per position), leave-one-season-out:")
for k,cat in C.CATS.items():
    D=build(k,cat); cols=FOCUS[k]; ev0=[];ev1=[];ey0=[];ey1=[]
    for s_ in SEAS:
        tr,te=D[D.season!=s_],D[D.season==s_]
        X1=np.column_stack([np.ones(len(tr)),tr[cols].values]); b=np.linalg.lstsq(X1,tr.r.values,rcond=None)[0]
        upl=np.column_stack([np.ones(len(te)),te[cols].values])@b            # predicted % change in volume vs baseline (incl. level)
        ev0+=list(te.act_v-te.base_v); ev1+=list(te.act_v-te.base_v*(1+upl))
        # carry the volume effect (centred: only the signal, not the level) into the yards projection
        sig=te[cols].values@b[1:]; ey0+=list(te.y-te.proj); ey1+=list(te.y-te.proj*(1+sig))
    print(f"  {k} ({cols[0]}): volume error {rm(ev0):.2f} -> {rm(ev1):.2f} ({(rm(ev1)/rm(ev0)-1)*100:+.1f}%)  |  YARDS error if the volume signal is added to the projection: {rm(ey0):.1f} -> {rm(ey1):.1f} ({(rm(ey1)/rm(ey0)-1)*100:+.1f}%)")
