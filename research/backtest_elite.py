"""Walk-forward test of Sheet 1: do top-N performers beat/miss their baseline against weak defenses?

For each past week W >= 4, using only games before W: take the top-10 at the position by season
yards, build the same baseline + defense factor the production code uses, and compare to what
happened in week W.  Parameters were tuned on 2023-24 and checked on 2025.

    python research/backtest_elite.py            # thesis test + production parameters
    python research/backtest_elite.py --tune     # grid search (slow-ish)
"""
from __future__ import annotations

import itertools
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from props import config as C                       # noqa: E402
from props.data import STAT_COLS, cached            # noqa: E402
from props.defense import matchup_beta, shrink     # noqa: E402
from props.gamescript import multiplier             # noqa: E402

warnings.filterwarnings("ignore")


def load(year):
    d = pd.read_csv(cached(f"stats_player/stats_player_week_{year}.csv", False),
                    usecols=lambda c: c in STAT_COLS)
    return d[d.season_type == "REG"].copy()


DATA = {}


def get(year):
    if year not in DATA:
        DATA[year] = load(year)
    return DATA[year]


def run(season, cat, K, k_def, lam, topn=10, start_wk=4):
    """Rows of (actual, baseline, defense factor, defense rank) for top-N players each week."""
    cur, prev = get(season), get(season - 1)
    c = cur[cur.position.isin(cat.positions)]
    dpos = cat.def_positions
    cd = cur if dpos is None else cur[cur.position.isin(dpos)]
    pdx = prev if dpos is None else prev[prev.position.isin(dpos)]
    allowed = cd.groupby(["opponent_team", "week"])[cat.yards].sum().reset_index()
    prev_pg = pdx.groupby(["opponent_team", "week"])[cat.yards].sum().groupby("opponent_team").mean()
    lg_prev = prev_pg.mean()
    pg = c[c[cat.volume].fillna(0) > 0][["player_id", "player_display_name", "team", "opponent_team",
                                         "week", cat.yards]].rename(columns={cat.yards: "y"})
    pp = prev[prev.position.isin(cat.positions) & (prev[cat.volume].fillna(0) > 0)]
    prev_p = pp.groupby("player_id")[cat.yards].agg(["mean", "size"])
    rows = []
    for w in range(start_wk, 19):
        tgt = pg[pg.week == w]
        if tgt.empty:
            continue
        hist = pg[pg.week < w]
        tot = hist.groupby("player_id").y.agg(["sum", "size", "mean"])
        top = tot.sort_values("sum", ascending=False).head(topn).index
        al = allowed[allowed.week < w].groupby("opponent_team")[cat.yards].agg(["mean", "size"])
        blend = {d: shrink(r["mean"], r["size"], lam * prev_pg.get(d, lg_prev) + (1 - lam) * lg_prev, k_def)
                 for d, r in al.iterrows()}
        bl = pd.Series(blend)
        rank = bl.rank(ascending=False, method="min")
        for prank, pid in enumerate(top, 1):
            t = tgt[tgt.player_id == pid]
            if t.empty:
                continue
            t = t.iloc[0]
            m, n = tot.loc[pid, "mean"], tot.loc[pid, "size"]
            l3 = hist[hist.player_id == pid].sort_values("week").y.tail(3).mean()
            pm = prev_p.loc[pid, "mean"] if pid in prev_p.index and prev_p.loc[pid, "size"] >= C.MIN_PRIOR_GAMES else m
            rows.append(dict(season=season, week=w, prank=prank, pid=pid, team=t.team, opp=t.opponent_team, l3=l3, y=t.y, ytd=m, base=shrink(m, n, pm, K),
                             f=bl.get(t.opponent_team, bl.mean()) / bl.mean(),
                             orank=rank.get(t.opponent_team, np.nan)))
    return pd.DataFrame(rows)


_LINES = None


def game_lines():
    """Closing spread / total per team-game: spread < 0 means the team is favoured (book notation)."""
    global _LINES
    if _LINES is None:
        g = pd.read_csv(cached("schedules/games.csv", True))
        g = g[g.game_type == "REG"]
        home = pd.DataFrame({"season": g.season, "week": g.week, "team": g.home_team, "home": True,
                             "spread": -g.spread_line, "ou": g.total_line})
        away = pd.DataFrame({"season": g.season, "week": g.week, "team": g.away_team, "home": False,
                             "spread": g.spread_line, "ou": g.total_line})
        _LINES = pd.concat([home, away], ignore_index=True)
    return _LINES


def add_projection(df, pull, beta=None, cat_key=None):
    """Production projection: shrunk baseline x matchup (x game script for categories that use it).

    beta=None -> the production rank-tiered matchup weight (needs cat_key and df.prank).
    """
    gm = df.groupby(["season", "week"]).base.transform("mean")
    base = (1 - pull) * df.base + pull * gm
    if beta is None:
        beta = np.asarray([matchup_beta(cat_key, int(r)) for r in df.prank])
    proj = base * (1 + beta * (df.f - 1))
    if cat_key in C.GAME_SCRIPT:
        ln = df[["season", "week", "team"]].merge(game_lines(), on=["season", "week", "team"], how="left")
        proj = proj * np.asarray([multiplier(cat_key, sp, o, h) for sp, o, h in zip(ln.spread, ln.ou, ln.home)])
    return proj


def thesis(seasons=(2023, 2024, 2025)):
    print("== Do elite players do better against weak defenses?  (QB top 10, RB top 15, WR top 25 YTD; weeks 4-18, 2023-25) ==")
    for k, cat in C.CATS.items():
        df = pd.concat([run(s, cat, C.PLAYER_PRIOR_GAMES, C.DEF_PRIOR_GAMES, C.DEF_PRIOR_REGRESS, topn=cat.elite_n)
                        for s in seasons])
        print(f"\n{k} (top {cat.elite_n}): n={len(df)}")
        for name, sub in (("weak D (worst 10)", df[df.orank <= 10]),
                          ("middle", df[(df.orank > 10) & (df.orank < 23)]),
                          ("strong D (best 10)", df[df.orank >= 23])):
            print(f"  {name:20s} n={len(sub):4d}  avg actual={sub.y.mean():6.1f}  avg baseline={sub.base.mean():6.1f}"
                  f"  actual/baseline={sub.y.mean() / sub.base.mean():.3f}")
        slope = np.polyfit(df.f - 1, df.y / df.base - 1, 1)[0]
        print(f"  pass-through of the defense edge (slope): {slope:.2f}")


def production_check():
    print("\n== Production parameters, 2025 hold-out vs naive season-to-date average ==")
    for k, cat in C.CATS.items():
        df = run(2025, cat, C.PLAYER_PRIOR_GAMES, C.DEF_PRIOR_GAMES, C.DEF_PRIOR_REGRESS, topn=cat.elite_n)
        proj = add_projection(df, C.ELITE_GROUP_PULL, None, k)
        rm = lambda e: float(np.sqrt(np.mean(e ** 2)))                   # noqa: E731
        print(f"  {k}: RMSE model={rm(df.y - proj):.1f} naive={rm(df.y - df.ytd):.1f} | "
              f"bias model={np.mean(df.y - proj):+.1f} naive={np.mean(df.y - df.ytd):+.1f}")


def tune():
    print("\n== Grid (train 2023-24, RMSE pooled over QB/RB/WR) ==")
    rows = []
    for k, cat in C.CATS.items():
        for K, kd in itertools.product((0, 3, 6, 10, 16), (3, 6, 10)):
            df = pd.concat([run(s, cat, K, kd, C.DEF_PRIOR_REGRESS) for s in (2023, 2024)])
            for pull, beta in itertools.product((0.0, 0.3, 0.6), (0.0, 0.25, 0.5, 0.75, 1.0)):
                e = df.y - add_projection(df, pull, beta)
                rows.append(dict(pos=k, K=K, kd=kd, pull=pull, beta=beta, mse=np.mean(e ** 2)))
    R = pd.DataFrame(rows)
    pooled = R.groupby(["K", "kd", "pull", "beta"]).mse.mean().pow(0.5).sort_values().head(8)
    print(pooled.round(2))


if __name__ == "__main__":
    thesis()
    production_check()
    if "--tune" in sys.argv:
        tune()
