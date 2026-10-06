"""Does "freshness" generalize?  Teammates out, first missed game vs a longer absence.

experiment_qb_out.py found that a QB's absence moves his receivers only in his FIRST missed game: afterwards the
season averages the projections are built from already contain it.  The touches experiment counted every absence.
Here the same walk-forward pools (2022-25, weeks 4+; top-25 WR, top-12 TE, top-15 RB) are tested against the share
of the team's volume held by key teammates who may miss the game, split by how many games they have already missed.

  v_fresh  sum over key teammates of P(out) x share, for those who played the team's previous game
  v_cont   the same for teammates who had already missed 1+ games
  QB-out   the QB flag from experiment_qb_out.py, as a control so QB events cannot masquerade as teammate effects

A key teammate: WR/TE/RB with 10%+ of the team's targets (volume pool "targets"), or an RB with 15%+ of RB carries
(pool "rb"), the thresholds props/backups.py uses.  P(out) comes from the pre-game injury report (Out/Doubtful 1.0,
Questionable at the calibrated rate); "ex-post" uses whether the teammate actually did not play.  Receivers' targets
and receptions respond to the targets pool; RB carries and rushing yards to the RB carries pool.
t-stats are clustered by team-game.

    python research/experiment_fresh_absence.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import walkforward_pool as W

GROUPS = {
    "WR": dict(positions=("WR",), topn=25, vol_col="targets", rank_col="receiving_yards",
               outcomes=[("targets", "targets"), ("receptions", "targets"), ("receiving_yards", "targets")]),
    "TE": dict(positions=("TE",), topn=12, vol_col="targets", rank_col="receiving_yards",
               outcomes=[("targets", "targets"), ("receptions", "targets"), ("receiving_yards", "targets")]),
    "RB": dict(positions=("RB", "FB"), topn=15, vol_col="carries", rank_col="rushing_yards",
               outcomes=[("carries", "rb"), ("rushing_yards", "rb"), ("targets", "targets")]),
}


def vacated(d: pd.DataFrame, ab: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Per pool row: expected share of the team's volume vacated by key teammates, split fresh vs continuing."""
    by = {k: list(zip(g.pid, g.share, g.p_out, g.ex_out, g.streak)) for k, g in ab.groupby(["season", "team", "week"])}
    vf, vc = [], []
    for s, t, w, pid in zip(d.season, d.team, d.week, d.pid):
        f = c = 0.0
        for j, share, p, ex, streak in by.get((s, t, w), []):
            if j == pid:
                continue
            x = share * (p if mode == "forward" else float(ex))
            if streak == 0:
                f += x
            else:
                c += x
        vf.append(f)
        vc.append(c)
    return pd.DataFrame({"v_fresh": vf, "v_cont": vc}, index=d.index)


def loso(x: pd.DataFrame, o: str, feats: list) -> float:
    """Leave-one-season-out RMSE change from scaling the baseline by (1 + sum of coefficients x features)."""
    e0, e1 = [], []
    for s in W.SEASONS:
        tr, te = x[x.season != s], x[x.season == s]
        b, _ = W.ols(tr[feats].values, (tr[o] / tr["base_" + o] - 1).values)
        e0 += list(te[o] - te["base_" + o])
        e1 += list(te[o] - te["base_" + o] * (1 + te[feats].values @ b[1:]))
    return W.rmse(e1) / W.rmse(e0) - 1


def main() -> None:
    ctx = pd.concat([W.qb_context(s) for s in W.SEASONS], ignore_index=True)[["season", "team", "week", "p_fresh"]]
    ctx = ctx.rename(columns={"p_fresh": "qb_fresh"})
    ab = {k: pd.concat([W.absences(s, k) for s in W.SEASONS], ignore_index=True) for k in ("targets", "rb")}

    print("== Key teammates who may miss a game (weeks 4+, 2022-25) ==")
    for k, a in ab.items():
        f, c = a[a.streak == 0], a[a.streak > 0]
        print(f"  pool '{k}': first missed game: listed {int((f.p_out > 0).sum())}, actually out {int(f.ex_out.sum())}"
              f"   |   already missed 1+: listed {int((c.p_out > 0).sum())}, actually out {int(c.ex_out.sum())}")

    for mode in ("forward", "ex-post"):
        title = ("FORWARD: P(out) from the pre-game injury report (coefficient = change in r per 100% of the team's volume vacated)"
                 if mode == "forward" else "EX-POST: key teammate actually did not play")
        print(f"\n===== {title} =====")
        print(f"{'':4s}{'outcome':16s}{'pool':8s}{'rows':>6s}{'fresh':>6s}{'games':>7s}{'cont':>6s}{'b fresh (t)':>16s}{'b cont (t)':>15s}{'b pooled (t)':>16s}"
              f"{'LOSO: fresh+cont':>18s}{'pooled':>9s}{'QB only':>9s}")
        for k, g in GROUPS.items():
            d = pd.concat([W.pool(s, g["positions"], g["topn"], [o for o, _ in g["outcomes"]], g["vol_col"], g["rank_col"])
                           for s in W.SEASONS], ignore_index=True)
            d = d.merge(ctx, on=["season", "team", "week"], how="left").fillna({"qb_fresh": 0.0})
            d["game"] = d.season.astype(str) + d.team + d.week.astype(str)
            for o, kind in g["outcomes"]:
                x = d.join(vacated(d, ab[kind], "forward" if mode == "forward" else "ex"))
                x = x[x["base_" + o] > 0].copy()
                x["v_all"] = x.v_fresh + x.v_cont
                y = (x[o] / x["base_" + o] - 1).values
                nf, ng, nc = int((x.v_fresh > 0).sum()), x.loc[x.v_fresh > 0, "game"].nunique(), int((x.v_cont > 0).sum())
                if ng < 8:
                    print(f"{k:4s}{o:16s}{kind:8s}{len(x):6d}{nf:6d}{ng:7d}{nc:6d}   (too few fresh games)")
                    continue
                b, t = W.ols(x[["v_fresh", "v_cont", "qb_fresh"]].values, y, cluster=x.game.values)
                ba, ta = W.ols(x[["v_all", "qb_fresh"]].values, y, cluster=x.game.values)
                print(f"{k:4s}{o:16s}{kind:8s}{len(x):6d}{nf:6d}{ng:7d}{nc:6d}{b[1]:+10.2f} ({t[1]:+4.1f}){b[2]:+9.2f} ({t[2]:+4.1f})"
                      f"{ba[1]:+10.2f} ({ta[1]:+4.1f}){loso(x, o, ['v_fresh', 'v_cont', 'qb_fresh']) * 100:+17.1f}%"
                      f"{loso(x, o, ['v_all', 'qb_fresh']) * 100:+8.1f}%{loso(x, o, ['qb_fresh']) * 100:+8.1f}%")


if __name__ == "__main__":
    main()
