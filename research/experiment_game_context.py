"""Does game context (spread/total, weather, rest, home field, recent form) improve the Sheet 1 projection?

Leave-one-season-out over 2022-25 on the walk-forward top-10 sets.  Result (see README): implied team total and
home field help QB/WR by 1-3%; nothing helps RB; weather, rest and recent form are noise.
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

g=pd.read_csv(cached("schedules/games.csv", True)); g=g[(g.game_type=="REG")&g.season.between(2022,2025)]
def side(df, home):
    t=pd.DataFrame({"season":df.season,"week":df.week,"team":df.home_team if home else df.away_team,"home":int(home)})
    fav=df.spread_line if home else -df.spread_line          # points this team is favoured by
    t["fav"]=fav; t["total"]=df.total_line; t["team_total"]=df.total_line/2+fav/2
    dome=df.roof.isin(["dome","closed"]); t["dome"]=dome.astype(int)
    t["wind"]=np.where(dome,0,df.wind.fillna(0)); t["temp"]=np.where(dome,70,df.temp.fillna(65))
    t["rest"]=(df.home_rest if home else df.away_rest); t["rest_diff"]=(df.home_rest-df.away_rest) if home else (df.away_rest-df.home_rest)
    return t
tg=pd.concat([side(g,True),side(g,False)])

rows=[]
for k,cat in C.CATS.items():
    for s in (2022,2023,2024,2025):
        d=BE.run(s,cat,C.PLAYER_PRIOR_GAMES,C.DEF_PRIOR_GAMES,C.DEF_PRIOR_REGRESS)
        d["proj0"]=BE.add_projection(d,C.ELITE_GROUP_PULL,C.MATCHUP_BETA); d["cat"]=k; rows.append(d)
D=pd.concat(rows).merge(tg,on=["season","week","team"],how="left")
D["tt_r"]=D.team_total/22.5-1; D["fav7"]=D.fav/7; D["tot_r"]=D.total/45-1; D["wind10"]=np.minimum(D.wind,25)/10
D["rest_d"]=D.rest_diff.clip(-4,4)/3; D["form"]=(D.l3/D.ytd-1).clip(-.6,.6)
D["r"]=D.y/D.proj0-1
print("rows:",len(D), D.groupby("cat").size().to_dict(), "| missing game ctx:", int(D.team_total.isna().sum()))
D=D.dropna(subset=["team_total","l3"])

SETS={"script: implied team total":["tt_r"],
      "script: favourite margin":["fav7"],
      "script: tt + margin":["tt_r","fav7"],
      "total only":["tot_r"],
      "weather: wind + dome":["wind10","dome"],
      "home field":["home"],
      "rest differential":["rest_d"],
      "recent form (L3 vs YTD)":["form"],
      "ALL game context (no form)":["tt_r","fav7","wind10","dome","home","rest_d"],
      "ALL incl. form":["tt_r","fav7","wind10","dome","home","rest_d","form"]}
def ols(X,y):
    X=np.column_stack([np.ones(len(X)),X]); b=np.linalg.lstsq(X,y,rcond=None)[0]; return b
rm=lambda e: float(np.sqrt(np.mean(e**2)))
print(f"\n{'feature set':30s}"+"".join(f"{k:>22s}" for k in C.CATS))
print(f"{'':30s}"+"".join(f"{'RMSE chg / MAE chg':>22s}" for _ in C.CATS))
res={}
for name,feats in SETS.items():
    line=f"{name:30s}"
    for k in C.CATS:
        d=D[D.cat==k]; e0=[];e1=[]
        for s in (2022,2023,2024,2025):               # leave-one-season-out
            tr,te=d[d.season!=s],d[d.season==s]
            b=ols(tr[feats].values,tr.r.values); pred=te.proj0*(1+np.column_stack([np.ones(len(te)),te[feats].values])@b)
            e0+=list(te.y-te.proj0); e1+=list(te.y-pred)
        e0,e1=np.array(e0),np.array(e1)
        res[(name,k)]=(rm(e1)/rm(e0)-1, np.mean(abs(e1))/np.mean(abs(e0))-1)
        line+=f"{res[(name,k)][0]*100:+10.1f}% /{res[(name,k)][1]*100:+6.1f}% "
    print(line)
print("\nBase RMSE (current model):",{k:round(rm(D[D.cat==k].y-D[D.cat==k].proj0),1) for k in C.CATS})
print("\nCoefficients on (actual/proj - 1), fit on all 4 seasons (t-stats):")
for name in ("script: implied team total","script: favourite margin","weather: wind + dome","home field","recent form (L3 vs YTD)"):
    feats=SETS[name]; out=[]
    for k in C.CATS:
        d=D[D.cat==k]; X=np.column_stack([np.ones(len(d)),d[feats].values]); y=d.r.values
        b=np.linalg.lstsq(X,y,rcond=None)[0]; res_=y-X@b; cov=np.linalg.inv(X.T@X)*res_.var(ddof=X.shape[1]); t=b/np.sqrt(np.diag(cov))
        out.append(f"{k}: "+", ".join(f"{f}={b[i+1]:+.3f}(t={t[i+1]:+.1f})" for i,f in enumerate(feats)))
    print(f"  {name:28s} "+" | ".join(out))
