"""Defensive ratings: how many yards each defense allows to a position group."""
from __future__ import annotations

import pandas as pd

from . import config as C
from .config import Category


def shrink(x, n, prior, k):
    """Blend a sample mean x (n observations) with a prior worth k observations."""
    n = 0 if pd.isna(n) else n
    if n + k <= 0:
        return prior
    if pd.isna(x):
        return prior
    return (n * x + k * prior) / (n + k)


def allowed_by_game(stats: pd.DataFrame, cat: Category) -> pd.DataFrame:
    """Yards each defense allowed to the position group in each game."""
    s = stats if cat.def_positions is None else stats[stats.position.isin(cat.def_positions)]
    out = s.groupby(["opponent_team", "week"])[cat.yards].sum().reset_index()
    return out.rename(columns={"opponent_team": "defense", cat.yards: "allowed"})


def defense_ratings(stats: pd.DataFrame, prev_stats: pd.DataFrame, cat: Category) -> pd.DataFrame:
    """Blended yards-allowed-per-game for all 32 defenses.

    Current-season per-game average, shrunk toward a prior built from last season
    (itself pulled halfway to the league mean, since defenses turn over).
    Columns: defense, games, cur_pg, blend, factor (blend / league), vs_lg (factor-1), rank
    where rank 1 = allows the MOST yards (weakest defense).
    """
    cur = allowed_by_game(stats, cat).groupby("defense").allowed.agg(cur_pg="mean", games="size")
    teams = sorted(set(stats.team) | set(stats.opponent_team)) if len(stats) else []
    cur = cur.reindex(teams)
    if len(prev_stats):
        prev = allowed_by_game(prev_stats, cat).groupby("defense").allowed.mean()
        lg_prev = prev.mean()
        prior = (C.DEF_PRIOR_REGRESS * prev.reindex(cur.index).fillna(lg_prev)
                 + (1 - C.DEF_PRIOR_REGRESS) * lg_prev)
    else:
        prior = pd.Series(cur.cur_pg.mean(), index=cur.index)
    cur["games"] = cur.games.fillna(0)
    blend = [shrink(x, n, p, C.DEF_PRIOR_GAMES)
             for x, n, p in zip(cur.cur_pg, cur.games, prior)]
    cur["blend"] = blend
    cur["factor"] = cur.blend / cur.blend.mean()
    cur["vs_lg"] = cur.factor - 1
    cur["rank"] = cur.blend.rank(ascending=False, method="min").astype(int)
    return cur.reset_index(names="defense")
