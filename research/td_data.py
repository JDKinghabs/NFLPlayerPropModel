"""Touchdown-opportunity data for experiment_td.py and fit_td_model.py.

The feature code lives in props/td.py (production uses the same functions, so research and the site cannot drift apart); this
module only adds what research needs on top: per-season loaders, the market's team total, and the opponent check.

  pbp(year)          cleaned play-by-play for one season
  td_rates(years)    P(TD) per rush / per target by distance to the end zone, from the seasons you pass in
  player_weeks()     per player-game: expected TDs from field position and red-zone usage
  universe(year)     one row per skill-position player-game from the weekly stats, with the anytime-TD outcome
  team_totals()      implied points per team per game from the closing spread and total (free, complete history)
  pregame()          season-to-date per-game means of each feature, shrunk toward last season, using earlier games only
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import walkforward_pool as W
from props import config as C
from props import td as TD
from props.data import cached

GROUPS = ("QB", "RB", "WR", "TE")                      # research also fits QBs; production does not
MIN_TOUCH = TD.MIN_TOUCH
FEATS = TD.FEATS
pregame = TD.pregame
bucket = TD.bucket

_PBP: dict = {}


def pbp(year: int) -> pd.DataFrame:
    if year not in _PBP:
        _PBP[year] = TD.read_pbp(cached(f"pbp/play_by_play_{year}.csv.gz", False))
    return _PBP[year]


def td_rates(years):
    return TD.td_rates([pbp(y) for y in years])


def player_weeks(year: int, rr, rt) -> pd.DataFrame:
    return TD.player_weeks(pbp(year), rr, rt)


def universe(year: int) -> pd.DataFrame:
    return TD.universe(W.stats(year))


def team_totals() -> pd.DataFrame:
    """Implied points for each team in each game: total / 2 + points favoured / 2 (nflverse spread_line > 0 = home favoured)."""
    g = pd.read_csv(cached("schedules/games.csv", True))
    g = g[g.game_type == "REG"]
    home = pd.DataFrame({"season": g.season, "week": g.week, "team": g.home_team, "tt": g.total_line / 2 + g.spread_line / 2})
    away = pd.DataFrame({"season": g.season, "week": g.week, "team": g.away_team, "tt": g.total_line / 2 - g.spread_line / 2})
    return pd.concat([home, away], ignore_index=True)


def opp_allowed(u: pd.DataFrame, k: float = C.DEF_PRIOR_GAMES) -> pd.DataFrame:
    """`opp_rel`: TDs a defense has allowed per game to a position group, relative to the league, using earlier games only
    (shrunk toward last season's number, itself pulled halfway to the league mean, as props/defense.py does)."""
    a = u.groupby(["season", "week", "opponent_team", "grp"]).td.sum().reset_index()
    a = a.rename(columns={"opponent_team": "defense", "td": "allowed"})
    a = a.sort_values(["defense", "grp", "season", "week"]).reset_index(drop=True)
    g = a.groupby(["defense", "grp", "season"])
    a["n_prev"] = g.cumcount()
    a["mean_prev"] = ((g.allowed.cumsum() - a.allowed) / a.n_prev.replace(0, np.nan)).fillna(0)
    pm = a.groupby(["defense", "grp", "season"]).allowed.mean().reset_index().rename(columns={"allowed": "pm"})
    lg = a.groupby(["grp", "season"]).allowed.mean().reset_index().rename(columns={"allowed": "lgm"})
    pm["season"] += 1
    lg["season"] += 1
    a = a.merge(pm, on=["defense", "grp", "season"], how="left").merge(lg, on=["grp", "season"], how="left")
    prior = C.DEF_PRIOR_REGRESS * a.pm.fillna(a.lgm) + (1 - C.DEF_PRIOR_REGRESS) * a.lgm
    a["opp_rel"] = ((a.n_prev * a.mean_prev + k * prior) / (a.n_prev + k)) / a.lgm
    return a[["season", "week", "defense", "grp", "opp_rel"]]
