"""Do the role columns nflverse already ships (and props/data.py discards) predict what the baseline misses?

Walk-forward over 2022-25 (weeks 4+): top-25 WR, top-12 TE, top-15 RB by season yards.  The baseline for each outcome is
the production-style shrunk per-game average.  Target r = actual / baseline - 1.  Features use only earlier games:

  share level   target share, air-yards share, WOPR (season to date)
  share trend   last 3 games vs season (relative change in target share / air-yards share / WOPR)
  depth         average depth of target (air yards per target)
  efficiency    yards per target (a high number regresses; a low one rebounds)

Each feature is tested alone (clustered t) and in sets with leave-one-season-out error.  The benchmark is the baseline
plus a constant level correction, so a gain means the features carry information, not that the level was off.

    python research/experiment_role_features.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import walkforward_pool as W

EXTRA = ("target_share", "air_yards_share", "wopr", "receiving_air_yards", "targets", "receiving_yards")
GROUPS = {
    "WR": dict(positions=("WR",), topn=25, vol_col="targets", rank_col="receiving_yards",
               outcomes=["receiving_yards", "targets", "receptions"]),
    "TE": dict(positions=("TE",), topn=12, vol_col="targets", rank_col="receiving_yards",
               outcomes=["receiving_yards", "targets", "receptions"]),
    "RB": dict(positions=("RB", "FB"), topn=15, vol_col="carries", rank_col="rushing_yards",
               outcomes=["rushing_yards", "carries", "targets", "receiving_yards"]),
}
# WOPR is 1.5 x target share + 0.7 x air-yards share, so it is tested alone but kept out of the multi-feature sets.
SETS = {
    "share level": ["ts", "ays"],
    "share trend": ["ts_tr", "ays_tr"],
    "depth": ["adot"],
    "efficiency": ["ypt"],
    "ALL": ["ts", "ays", "ts_tr", "ays_tr", "adot", "ypt"],
}
SINGLE = ["ts", "ays", "wopr", "ts_tr", "ays_tr", "wopr_tr", "adot", "ypt"]


def features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    tr = lambda l3, ytd: (l3 / ytd.clip(lower=0.02) - 1).clip(-1, 1)         # noqa: E731
    d["ts"], d["ays"], d["wopr"] = d.ytd_target_share, d.ytd_air_yards_share, d.ytd_wopr
    d["ts_tr"] = tr(d.l3_target_share, d.ytd_target_share)
    d["ays_tr"] = tr(d.l3_air_yards_share, d.ytd_air_yards_share)
    d["wopr_tr"] = tr(d.l3_wopr, d.ytd_wopr)
    d["adot"] = d.sum_receiving_air_yards / d.sum_targets.clip(lower=1)
    d["ypt"] = d.sum_receiving_yards / d.sum_targets.clip(lower=1)
    return d


def loso(x: pd.DataFrame, o: str, feats: list) -> float:
    """RMSE of (baseline x (1 + level + features)) over RMSE of (baseline x (1 + level)), leave-one-season-out."""
    e0, e1 = [], []
    for s in W.SEASONS:
        tr, te = x[x.season != s], x[x.season == s]
        mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
        ztr, zte = ((tr[feats] - mu) / sd).values, ((te[feats] - mu) / sd).values
        y = (tr[o] / tr["base_" + o] - 1).values
        b0, _ = W.ols(np.zeros((len(tr), 0)), y)
        b1, _ = W.ols(ztr, y)
        e0 += list(te[o] - te["base_" + o] * (1 + b0[0]))
        e1 += list(te[o] - te["base_" + o] * (1 + b1[0] + zte @ b1[1:]))
    return W.rmse(e1) / W.rmse(e0) - 1


def main() -> None:
    allf = SINGLE
    for k, g in GROUPS.items():
        d = pd.concat([W.pool(s, g["positions"], g["topn"], g["outcomes"], g["vol_col"], g["rank_col"], extra=EXTRA)
                       for s in W.SEASONS], ignore_index=True)
        d = features(d).dropna(subset=allf)
        d["game"] = d.season.astype(str) + d.team + d.week.astype(str)
        print(f"\n===== {k}: {len(d)} walk-forward player-games =====")
        print(f"{'outcome':17s}" + "".join(f"{f:>10s}" for f in allf) + "   <- clustered t of each feature alone")
        for o in g["outcomes"]:
            x = d[d["base_" + o] > 0].copy()
            y = (x[o] / x["base_" + o] - 1).values
            ts = []
            for f in allf:
                z = ((x[f] - x[f].mean()) / x[f].std()).values[:, None]
                _, t = W.ols(z, y, cluster=x.game.values)
                ts.append(t[1])
            print(f"{o:17s}" + "".join(f"{t:+10.1f}" for t in ts))
        print(f"\n{'LOSO RMSE change':17s}" + "".join(f"{n:>14s}" for n in SETS) + "   <- vs baseline + constant level")
        for o in g["outcomes"]:
            x = d[d["base_" + o] > 0]
            print(f"{o:17s}" + "".join(f"{loso(x, o, fs) * 100:+13.1f}%" for fs in SETS.values()))


if __name__ == "__main__":
    main()
