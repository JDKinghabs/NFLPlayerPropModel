"""Does the starting QB being out change what his pass-catchers do?

The production model adjusts nothing for it: a WR/TE/RB projection is the same whether his QB is Questionable, Out, or
fine.  Walk-forward over 2022-25 (weeks 4+): top-25 WR, top-12 TE and top-15 RB by season yards, baseline = shrunk
per-game average of each outcome (yards, targets, receptions; RB also carries and rushing yards).

Flags (the "starter" is the QB with the most attempts for the team earlier in the season):
  ex-post   starter threw under half the team's attempts in the game (diagnostic: the effect when he really is out)
  forward   P(starter out) from his pre-game injury-report status: Out/Doubtful 1.0, Questionable at the calibrated QB
            rate (props/config.py).  This is what a pre-game tool can actually know.
  fresh     only when he played the team's previous game.  A longer absence is already inside the season averages.

Every t-stat is clustered by team-game: all the receivers of one team share one QB event, so the independent sample
is the number of team-games, not the number of player-games.

    python research/experiment_qb_out.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import walkforward_pool as W

GROUPS = {
    "WR": dict(positions=("WR",), topn=25, vol_col="targets", rank_col="receiving_yards",
               outcomes=["receiving_yards", "targets", "receptions"]),
    "TE": dict(positions=("TE",), topn=12, vol_col="targets", rank_col="receiving_yards",
               outcomes=["receiving_yards", "targets", "receptions"]),
    "RB": dict(positions=("RB", "FB"), topn=15, vol_col="carries", rank_col="rushing_yards",
               outcomes=["rushing_yards", "carries", "receiving_yards", "targets", "receptions"]),
}


def build() -> tuple[dict, pd.DataFrame]:
    ctx = pd.concat([W.qb_context(s) for s in W.SEASONS], ignore_index=True)
    out = {}
    for k, g in GROUPS.items():
        d = pd.concat([W.pool(s, g["positions"], g["topn"], g["outcomes"], g["vol_col"], g["rank_col"])
                       for s in W.SEASONS], ignore_index=True)
        d = d.merge(ctx, on=["season", "team", "week"], how="inner")
        d["game"] = d.season.astype(str) + d.team + d.week.astype(str)
        out[k] = d
    return out, ctx


def loso(d: pd.DataFrame, o: str, flag: str) -> tuple[float, float]:
    """Leave-one-season-out change in RMSE / MAE (outcome units) from scaling the baseline by (1 + b * flag)."""
    e0, e1 = [], []
    for s in W.SEASONS:
        tr, te = d[d.season != s], d[d.season == s]
        b, _ = W.ols(tr[[flag]].values.astype(float), (tr[o] / tr["base_" + o] - 1).values)
        e0 += list(te[o] - te["base_" + o])
        e1 += list(te[o] - te["base_" + o] * (1 + b[1] * te[flag].astype(float)))
    e0, e1 = np.array(e0), np.array(e1)
    return W.rmse(e1) / W.rmse(e0) - 1, np.mean(abs(e1)) / np.mean(abs(e0)) - 1


def table(groups: dict, flag: str, title: str, outs: dict | None = None) -> None:
    print(f"\n== {title} ==")
    print(f"{'':4s}{'outcome':17s}{'rows':>6s}{'flag':>6s}{'games':>7s}{'mean r | flag':>15s}{'| not':>8s}{'effect (clustered t)':>24s}{'LOSO RMSE':>11s}{'MAE':>8s}")
    for k, d in groups.items():
        for o in (outs or {}).get(k, GROUPS[k]["outcomes"]):
            x = d[d["base_" + o] > 0].copy()
            x["r"] = x[o] / x["base_" + o] - 1
            f = x[flag].astype(float)
            nf, ng = int((f > 0).sum()), x.loc[f > 0, "game"].nunique()
            if ng < 8:
                print(f"{k:4s}{o:17s}{len(x):6d}{nf:6d}{ng:7d}   (too few flagged games)")
                continue
            b, t = W.ols(f.values[:, None], x.r.values, cluster=x.game.values)
            rmse_chg, mae_chg = loso(x, o, flag)
            print(f"{k:4s}{o:17s}{len(x):6d}{nf:6d}{ng:7d}{x.r[f > 0].mean():+15.3f}{x.r[f == 0].mean():+8.3f}"
                  f"{b[1]:+14.3f} ({t[1]:+5.1f}){rmse_chg * 100:+10.1f}%{mae_chg * 100:+7.1f}%")


def stability(groups: dict, flag: str, o: str = "receiving_yards", k: str = "WR") -> None:
    d = groups[k]
    d = d[d["base_" + o] > 0].copy()
    d["r"] = d[o] / d["base_" + o] - 1
    print(f"\n   {k} {o}, flag = {flag}, by season (games flagged / mean r flagged / mean r otherwise):")
    for s in W.SEASONS:
        x = d[d.season == s]
        f = x[flag].astype(float) > 0
        print(f"     {s}: {x.loc[f, 'game'].nunique():3d} / {x.r[f].mean() if f.any() else float('nan'):+.3f} / {x.r[~f].mean():+.3f}")


def main() -> None:
    groups, ctx = build()
    c = ctx[ctx.week >= 4]
    print("== The QB's pre-game injury designation vs what happened (all team-games, weeks 4+) ==")
    print(f"  team-games {len(c)}; starter out ex-post {int(c.starter_out.sum())}; first missed game {int(c.first_out.sum())}")
    for st in ("Out", "Doubtful", "Questionable", ""):
        sub = c[c.status == st]
        fr = sub[sub.streak == 0]
        print(f"  listed {st or '(nothing)':13s} n={len(sub):4d}  out ex-post {sub.starter_out.mean():4.0%}"
              f"   | first-game cases n={len(fr):4d}  out ex-post {fr.starter_out.mean() if len(fr) else float('nan'):4.0%}")
    print(f"  first missed games with NO report designation (benched / unreported): {int((c.first_out & (c.status == '')).sum())} of {int(c.first_out.sum())}")

    table(groups, "p_out", "Forward, any absence: P(starter out) from the injury report (effect per 100% probability)")
    table(groups, "p_fresh", "Forward, first missed game only: P(starter out) when he played last time  <- usable pre-game")
    stability(groups, "p_fresh")
    table(groups, "first_out", "Ex-post, first missed game (includes benchings and unreported absences)")
    stability(groups, "first_out")
    table(groups, "starter_out", "Ex-post, any absence (includes long-term replacements the market priced weeks ago)",
          outs={"WR": ["receiving_yards", "targets"], "TE": ["targets"], "RB": ["receiving_yards"]})


if __name__ == "__main__":
    main()
