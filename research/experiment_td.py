"""Anytime-TD probability: does field-position opportunity beat a player's TD history, and does the market's team total add?

Walk-forward over 2022-25 (week 4+), leave-one-season-out.  One row per skill-position player-game with a real role
(shrunk usage per game: RB 6+ carries+targets, WR 4+, TE 3+, QB 3+ rushes).  Outcome: scored a rushing or receiving TD.
All features use only earlier games (this season, shrunk toward last season):

  TD history      the player's anytime-TD frequency
  opportunity     expected TDs per game from where his rushes and targets started (league P(TD) by distance to the end zone,
                  estimated from the OTHER seasons only)
  team total      this game's implied points for his team, from the closing spread and total (free, complete history)
  volume          carries + targets per game

Models are logistic regressions fit per position on the other three seasons.  Scored by log loss and Brier; the paired
difference against the TD-history baseline carries a t-stat clustered by team-game.

    python research/experiment_td.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import td_data as T
import walkforward_pool as W

YEARS = (2021, 2022, 2023, 2024, 2025)
TEST = (2022, 2023, 2024, 2025)
MODELS = {
    "TD history": ["lt"],
    "opportunity (xTD)": ["lr", "lg"],
    "history + opportunity": ["lt", "lr", "lg"],
    "+ team total": ["lt", "lr", "lg", "ltt"],
    "+ volume": ["lt", "lr", "lg", "ltt", "lv"],
    "+ volume + opponent": ["lt", "lr", "lg", "ltt", "lv", "lo"],
}


def fit_logit(X: np.ndarray, y: np.ndarray, l2: float = 1.0):
    """Ridge logistic regression by Newton steps; returns (coefficients with intercept first, covariance)."""
    Xb = np.column_stack([np.ones(len(X)), X])
    pen = np.eye(Xb.shape[1]) * l2
    pen[0, 0] = 0.0
    b = np.zeros(Xb.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-(Xb @ b)))
        step = np.linalg.solve((Xb.T * (p * (1 - p))) @ Xb + pen, Xb.T @ (y - p) - pen @ b)
        b += step
        if np.abs(step).max() < 1e-9:
            break
    p = 1 / (1 + np.exp(-(Xb @ b)))
    return b, np.linalg.inv((Xb.T * (p * (1 - p))) @ Xb + pen)


def predict(b: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(np.column_stack([np.ones(len(X)), X]) @ b)))


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def design(d: pd.DataFrame, tt_mean: float) -> pd.DataFrame:
    f = pd.DataFrame(index=d.index)
    r = np.clip(d.pg_td, 0.02, 0.98)
    f["lt"] = np.log(r / (1 - r))
    f["lr"] = np.log(d.pg_rush_xtd + 0.02)
    f["lg"] = np.log(d.pg_tgt_xtd + 0.02)
    f["ltt"] = np.log(d.tt.fillna(tt_mean) / tt_mean)
    f["lv"] = np.log(d.pg_touch + 1)
    f["lo"] = np.log(d.opp_rel.fillna(1.0))
    return f


def build_fold(test_season: int, u: pd.DataFrame, tt: pd.DataFrame, oa: pd.DataFrame) -> pd.DataFrame:
    """All seasons' player-games with pre-game features; opportunity rates come from seasons other than `test_season`."""
    rr, rt = T.td_rates([y for y in YEARS if y != test_season])
    pw = pd.concat([T.player_weeks(y, rr, rt) for y in YEARS])
    d = u.merge(pw, on=["season", "week", "player_id"], how="left")
    d = d.fillna({c: 0 for c in ["rush_xtd", "tgt_xtd", "rush10", "rush5", "tgt20", "tgt10"]})
    d = T.pregame(d).merge(tt, on=["season", "week", "team"], how="left")
    d = d.merge(oa, left_on=["season", "week", "opponent_team", "grp"], right_on=["season", "week", "defense", "grp"], how="left")
    d["game"] = d.season.astype(str) + d.team + d.week.astype(str)
    return d[(d.week >= 4) & (d.pg_touch >= d.grp.map(T.MIN_TOUCH))]


def main() -> None:
    u = pd.concat([T.universe(y) for y in YEARS], ignore_index=True)
    tt = T.team_totals()
    tt_mean = float(tt[tt.season.isin(YEARS)].tt.mean())
    oa = T.opp_allowed(u)
    out = {g: [] for g in T.GROUPS}                                    # out-of-fold predictions per position
    for s in TEST:
        d = build_fold(s, u, tt, oa)
        for g in T.GROUPS:
            x = d[d.grp == g]
            tr, te = x[(x.season != s) & (x.season >= 2022)], x[x.season == s]
            Ftr, Fte = design(tr, tt_mean), design(te, tt_mean)
            row = te[["season", "week", "player_display_name", "team", "game", "td"]].copy()
            row["p_const"] = tr.td.mean()
            for name, cols in MODELS.items():
                mu, sd = Ftr[cols].mean(), Ftr[cols].std()
                b, _ = fit_logit(((Ftr[cols] - mu) / sd).values, tr.td.values)
                row["p_" + name] = predict(b, ((Fte[cols] - mu) / sd).values)
            out[g].append(row)

    print("== Anytime TD (rushing or receiving), out-of-fold 2022-25, weeks 4+ ==")
    base = "TD history"
    for g in T.GROUPS:
        r = pd.concat(out[g], ignore_index=True)
        y = r.td.values
        print(f"\n--- {g}: {len(r)} player-games, TD rate {y.mean():.3f}, {r.game.nunique()} team-games ---")
        print(f"{'model':24s}{'log loss':>10s}{'Brier':>9s}{'vs TD history':>16s}{'  clustered t':>14s}")
        ll_base = logloss(r["p_" + base].values, y)
        for name in ["const", base] + [m for m in MODELS if m != base and m != "+ volume + opponent"]:
            p = r["p_" + name].values if name != "const" else r.p_const.values
            ll = logloss(p, y)
            diff = ll - ll_base
            _, t = W.ols(np.zeros((len(r), 0)), diff, cluster=r.game.values)
            tag = f"{diff.mean() / ll_base.mean() * 100:+14.2f}%" if name != base else f"{'':>15s}"
            print(f"{name:24s}{ll.mean():10.4f}{np.mean((p - y) ** 2):9.4f}{tag}{t[0]:+12.1f}" if name != base
                  else f"{name:24s}{ll.mean():10.4f}{np.mean((p - y) ** 2):9.4f}{tag}")
        best = "+ volume"
        q = pd.qcut(r["p_" + best], 5, duplicates="drop")
        cal = r.groupby(q, observed=True).agg(n=("td", "size"), predicted=("p_" + best, "mean"), actual=("td", "mean"))
        print(f"  calibration of '{best}' by predicted-probability quintile:")
        for iv, c in cal.iterrows():
            print(f"    {str(iv):22s} n={int(c.n):5d}  predicted {c.predicted:5.1%}  actual {c.actual:5.1%}")

    print("\n== Stability: log-loss change of '+ volume' vs 'TD history' by test season (negative = better) ==")
    print(f"{'':4s}" + "".join(f"{s:>9d}" for s in TEST))
    for g in T.GROUPS:
        r = pd.concat(out[g], ignore_index=True)
        print(f"{g:4s}" + "".join(
            f"{(logloss(x['p_+ volume'].values, x.td.values).mean() / logloss(x['p_TD history'].values, x.td.values).mean() - 1) * 100:+8.2f}%"
            for s in TEST for x in [r[r.season == s]]))
    print("\n== Does the opponent's TDs-allowed rate add?  ('+ volume + opponent' vs '+ volume'; positive = worse) ==")
    for g in T.GROUPS:
        r = pd.concat(out[g], ignore_index=True)
        diff = logloss(r["p_+ volume + opponent"].values, r.td.values) - logloss(r["p_+ volume"].values, r.td.values)
        _, t = W.ols(np.zeros((len(r), 0)), diff, cluster=r.game.values)
        print(f"  {g}: {diff.mean() / logloss(r['p_+ volume'].values, r.td.values).mean() * 100:+.2f}% log loss, clustered t={t[0]:+.1f}")

    d = build_fold(2025, u, tt, oa)
    print("\n== Standardized coefficients, 'history + opportunity + team total', fit on all seasons 2022-25 (model-based z) ==")
    for g in T.GROUPS:
        x = d[(d.grp == g) & (d.season >= 2022)]
        F = design(x, tt_mean)[MODELS["+ team total"]]
        b, cov = fit_logit(((F - F.mean()) / F.std()).values, x.td.values)
        z = b / np.sqrt(np.diag(cov))
        print(f"  {g}: " + "  ".join(f"{c} {b[i + 1]:+.2f} (z={z[i + 1]:+.1f})" for i, c in enumerate(F.columns)))


if __name__ == "__main__":
    main()
