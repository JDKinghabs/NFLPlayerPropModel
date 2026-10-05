"""Defensive ratings: how many yards each defense allows to a position group."""
from __future__ import annotations

import pandas as pd

from . import config as C
from .config import Category
from .volume import touch_col


def shrink(x, n, prior, k):
    """Blend a sample mean x (n observations) with a prior worth k observations.

    No usable prior (a rookie, say) -> the sample mean; no sample -> the prior.
    """
    n = 0 if pd.isna(n) else n
    if pd.isna(prior):
        return x
    if pd.isna(x) or n + k <= 0:
        return prior
    return (n * x + k * prior) / (n + k)


def allowed_by_game(stats: pd.DataFrame, cat: Category, volume: bool = False) -> pd.DataFrame:
    """Yards (or, with volume=True, touches) each defense allowed to the position group in each game."""
    s = stats if cat.def_positions is None else stats[stats.position.isin(cat.def_positions)]
    s = s.assign(_v=touch_col(s, cat.key) if volume else s[cat.yards])
    out = s.groupby(["opponent_team", "week"])["_v"].sum().reset_index()
    return out.rename(columns={"opponent_team": "defense", "_v": "allowed"})


def _blend(cur_games: pd.DataFrame, prev_games: pd.DataFrame, teams: list) -> pd.DataFrame:
    """Per-game average allowed, shrunk toward a prior built from last season (itself pulled to the league mean)."""
    cur = cur_games.groupby("defense").allowed.agg(cur_pg="mean", games="size").reindex(teams)
    if len(prev_games):
        prev = prev_games.groupby("defense").allowed.mean()
        lg_prev = prev.mean()
        prior = (C.DEF_PRIOR_REGRESS * prev.reindex(cur.index).fillna(lg_prev)
                 + (1 - C.DEF_PRIOR_REGRESS) * lg_prev)
    else:
        prior = pd.Series(cur.cur_pg.mean(), index=cur.index)
    cur["games"] = cur.games.fillna(0)
    cur["blend"] = [shrink(x, n, p, C.DEF_PRIOR_GAMES) for x, n, p in zip(cur.cur_pg, cur.games, prior)]
    return cur


def defense_ratings(stats: pd.DataFrame, prev_stats: pd.DataFrame, cat: Category) -> pd.DataFrame:
    """Blended yards-allowed-per-game for all 32 defenses.

    Columns: defense, games, cur_pg, blend, factor (blend / league), vs_lg (factor-1), rank
    (rank 1 = allows the MOST yards = weakest defense), and vol_factor: the same blend for the VOLUME the
    defense faces (attempts / touches / targets), which is what predicts a QB's pass attempts.
    """
    teams = sorted(set(stats.team) | set(stats.opponent_team)) if len(stats) else []
    have_prev = len(prev_stats) > 0
    cur = _blend(allowed_by_game(stats, cat), allowed_by_game(prev_stats, cat) if have_prev else prev_stats, teams)
    cur["factor"] = cur.blend / cur.blend.mean()
    cur["vs_lg"] = cur.factor - 1
    cur["rank"] = cur.blend.rank(ascending=False, method="min").astype(int)
    vol = _blend(allowed_by_game(stats, cat, volume=True),
                 allowed_by_game(prev_stats, cat, volume=True) if have_prev else prev_stats, teams)
    cur["vol_factor"] = vol.blend / vol.blend.mean()
    return cur.reset_index(names="defense")


def matchup_beta(cat_key: str, rank: int) -> float:
    """How much of the defense's edge to pass through for a player of this season-yards rank."""
    for bound, beta in C.MATCHUP_BETA_TIERS.get(cat_key, [(10**6, C.MATCHUP_BETA)]):
        if rank <= bound:
            return beta
    return C.MATCHUP_BETA_TIERS[cat_key][-1][1]
