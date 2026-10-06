"""Fit the anytime-TD model that production uses and write props/td_model.json.

Same features and procedure as experiment_td.py (the '+ volume' model): per position (RB, WR, TE), a ridge logistic regression on
  lt   log-odds of the player's shrunk TD history      lr / lg   log expected TDs per game from his rushes / his targets
  ltt  log of the game's implied team total            lv        log of his carries + targets per game
fit on every test-eligible player-game of 2022-25 (weeks 4+).  Yard-line TD rates come from 2021-25.  The file also stores the
out-of-fold (leave-one-season-out) log loss and calibration so the numbers on the site can be checked against it.

    python research/fit_td_model.py            # rewrites props/td_model.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import td_data as T
import walkforward_pool as W
from experiment_td import YEARS, TEST, build_fold, fit_logit, logloss, predict as predict_b
from props import td as TD

OUT = Path(__file__).resolve().parent.parent / "props" / "td_model.json"


def standardize(F: pd.DataFrame, cols):
    mu, sd = F[cols].mean(), F[cols].std()
    return ((F[cols] - mu) / sd).values, mu, sd


def main() -> None:
    u = pd.concat([T.universe(y) for y in YEARS], ignore_index=True)
    tt = T.team_totals()
    tt_mean = float(tt[tt.season.isin(YEARS)].tt.mean())
    oa = T.opp_allowed(u)                                              # only needed by build_fold's signature
    rr, rt = T.td_rates(YEARS)

    # out-of-fold predictions: rates from the other seasons, model fit on the other three test seasons
    oof = {g: [] for g in TD.TD_GROUPS}
    for s in TEST:
        d = build_fold(s, u, tt, oa)
        for g in TD.TD_GROUPS:
            x = d[d.grp == g]
            tr, te = x[(x.season != s) & (x.season >= 2022)], x[x.season == s]
            Ftr, Fte = TD.design(tr, tt_mean), TD.design(te, tt_mean)
            Z, mu, sd = standardize(Ftr, TD.MODEL_FEATURES)
            b, _ = fit_logit(Z, tr.td.values)
            oof[g].append(pd.DataFrame({"td": te.td.values, "p": predict_b(b, ((Fte[TD.MODEL_FEATURES] - mu) / sd).values)}))

    # the production fit: rates from all seasons, every eligible player-game of 2022-25
    pw = pd.concat([T.player_weeks(y, rr, rt) for y in YEARS])
    d = TD.with_opportunity(u, pw)
    d = TD.pregame(d).merge(tt, on=["season", "week", "team"], how="left")
    d = d[(d.week >= 4) & (d.season >= 2022) & (d.pg_touch >= d.grp.map(TD.MIN_TOUCH))]
    model = {
        "version": date.today().isoformat(),
        "note": "anytime-TD model; see research/fit_td_model.py and research/experiment_td.py",
        "trained_on": [y for y in YEARS if y >= 2022], "rate_seasons": list(YEARS),
        "edges": TD.EDGES.tolist(), "rush_rate": np.round(rr, 6).tolist(), "tgt_rate": np.round(rt, 6).tolist(),
        "tt_mean": round(tt_mean, 4), "min_touch": TD.MIN_TOUCH, "features": TD.MODEL_FEATURES, "groups": {}, "oof": {},
    }
    for g in TD.TD_GROUPS:
        x = d[d.grp == g]
        F = TD.design(x, tt_mean)
        Z, mu, sd = standardize(F, TD.MODEL_FEATURES)
        b, _ = fit_logit(Z, x.td.values)
        model["groups"][g] = {"features": TD.MODEL_FEATURES, "mean": np.round(mu.values, 6).tolist(),
                              "sd": np.round(sd.values, 6).tolist(), "coef": np.round(b, 6).tolist(),
                              "n": int(len(x)), "td_rate": round(float(x.td.mean()), 4)}
        r = pd.concat(oof[g], ignore_index=True)
        q = pd.qcut(r.p, 5, duplicates="drop")
        cal = r.groupby(q, observed=True).agg(n=("td", "size"), predicted=("p", "mean"), actual=("td", "mean"))
        model["oof"][g] = {"n": int(len(r)), "log_loss": round(float(logloss(r.p.values, r.td.values).mean()), 4),
                           "calibration": [[round(float(c.predicted), 4), round(float(c.actual), 4), int(c.n)] for _, c in cal.iterrows()]}
        print(f"{g}: fit on {len(x)} player-games, TD rate {x.td.mean():.3f}; out-of-fold log loss {model['oof'][g]['log_loss']}; "
              "calibration (predicted -> actual): " + ", ".join(f"{p:.0%}->{a:.0%}" for p, a, _ in model["oof"][g]["calibration"]))
    OUT.write_text(json.dumps(model, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
