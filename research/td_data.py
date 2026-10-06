"""Touchdown-opportunity data for experiment_td.py: play-by-play -> expected TDs per player-game, plus the market's team total.

  td_rates()       P(TD) per rush / per pass target by distance from the end zone (league-wide, from the seasons you pass in)
  player_weeks()   per player-game: expected TDs from field position (rushes and targets) and red-zone usage
  universe()       one row per skill-position player-game from the weekly stats, with the anytime-TD outcome
  team_totals()    implied points per team per game from the closing spread and total (free, complete history)
  pregame()        season-to-date per-game means of each feature, shrunk toward last season, using earlier games only
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import walkforward_pool as W
from props import config as C
from props.data import cached

PBP_COLS = ["season", "week", "season_type", "posteam", "play_type", "yardline_100", "rusher_player_id", "receiver_player_id",
            "rush_touchdown", "pass_touchdown", "sack", "two_point_attempt"]
EDGES = np.array([1, 2, 3, 4, 6, 9, 13, 21, 36, 51])           # lower bounds of the yard-line buckets (yards from the end zone)
GROUPS = ("QB", "RB", "WR", "TE")
# players with a real role, by shrunk usage per game: carries+targets (RB/WR/TE), rushes (QB)
MIN_TOUCH = {"RB": 6.0, "WR": 4.0, "TE": 3.0, "QB": 3.0}

_PBP: dict = {}


def pbp(year: int) -> pd.DataFrame:
    if year not in _PBP:
        d = pd.read_csv(cached(f"pbp/play_by_play_{year}.csv.gz", False), usecols=lambda c: c in PBP_COLS, low_memory=False)
        _PBP[year] = d[(d.season_type == "REG") & (d.two_point_attempt.fillna(0) == 0) & d.yardline_100.notna()]
    return _PBP[year]


def bucket(y) -> np.ndarray:
    return np.clip(np.digitize(np.asarray(y, dtype=float), EDGES) - 1, 0, len(EDGES) - 1)


def plays(d: pd.DataFrame):
    rush = d[(d.play_type == "run") & d.rusher_player_id.notna()]
    tgt = d[(d.play_type == "pass") & d.receiver_player_id.notna() & (d.sack.fillna(0) == 0)]
    return rush, tgt


def td_rates(years) -> tuple[np.ndarray, np.ndarray]:
    """(P(TD) per rush, P(TD) per target) in each yard-line bucket, pooled over `years`."""
    r = pd.concat([plays(pbp(y))[0] for y in years])
    t = pd.concat([plays(pbp(y))[1] for y in years])
    n = len(EDGES)
    rr = r.groupby(bucket(r.yardline_100.values)).rush_touchdown.mean().reindex(range(n)).fillna(0).values
    rt = t.groupby(bucket(t.yardline_100.values)).pass_touchdown.mean().reindex(range(n)).fillna(0).values
    return rr, rt


def player_weeks(year: int, rr: np.ndarray, rt: np.ndarray) -> pd.DataFrame:
    """Per (season, week, player): rush_xtd / tgt_xtd (expected TDs from where the plays started), rush10, rush5, tgt20, tgt10."""
    rush, tgt = plays(pbp(year))
    key = ["season", "week", "player_id"]
    a = pd.DataFrame({"season": rush.season.values, "week": rush.week.values, "player_id": rush.rusher_player_id.values,
                      "rush_xtd": rr[bucket(rush.yardline_100.values)], "rush10": (rush.yardline_100.values <= 10).astype(int),
                      "rush5": (rush.yardline_100.values <= 5).astype(int)}).groupby(key).sum().reset_index()
    b = pd.DataFrame({"season": tgt.season.values, "week": tgt.week.values, "player_id": tgt.receiver_player_id.values,
                      "tgt_xtd": rt[bucket(tgt.yardline_100.values)], "tgt20": (tgt.yardline_100.values <= 20).astype(int),
                      "tgt10": (tgt.yardline_100.values <= 10).astype(int)}).groupby(key).sum().reset_index()
    return a.merge(b, on=key, how="outer").fillna(0)


def universe(year: int) -> pd.DataFrame:
    """Skill-position player-games from the weekly stats; td = scored a rushing or receiving TD (the anytime-TD market)."""
    s = W.stats(year)
    s = s[s.position.isin(["QB", "RB", "FB", "WR", "TE"])].copy()
    s["grp"] = s.position.replace({"FB": "RB"})
    car, tg = s.carries.fillna(0), s.targets.fillna(0)
    s["touch"] = np.where(s.grp == "QB", car, car + tg)
    played = np.where(s.grp == "QB", s.attempts.fillna(0) > 0, s.touch > 0)
    s = s[played].copy()
    s["td"] = ((s.rushing_tds.fillna(0) + s.receiving_tds.fillna(0)) >= 1).astype(int)
    return s[["season", "week", "player_id", "player_display_name", "grp", "team", "opponent_team", "touch", "td"]]


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


FEATS = ["td", "rush_xtd", "tgt_xtd", "touch", "rush10", "tgt20"]


def pregame(df: pd.DataFrame, k: float = C.PLAYER_PRIOR_GAMES) -> pd.DataFrame:
    """Add `pg_<feature>`: per-game mean of each feature over the player's EARLIER games this season, shrunk toward his
    per-game mean last season (if he played MIN_PRIOR_GAMES+ games), else toward last season's mean for his position.
    `n_prev` = earlier games this season.  df needs season, week, player_id, grp and the FEATS columns.
    """
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    g = df.groupby(["player_id", "season"])
    df["n_prev"] = g.cumcount()
    # last season's per-player and per-position means, re-keyed to the season they will serve as a prior for
    me = df.groupby(["player_id", "season"]).agg(**{f: (f, "mean") for f in FEATS}, size=("td", "size")).reset_index()
    me["season"] += 1
    me = me.rename(columns={f: "pl_" + f for f in FEATS})
    me.loc[me["size"] < C.MIN_PRIOR_GAMES, ["pl_" + f for f in FEATS]] = np.nan
    po = df.groupby(["season", "grp"])[FEATS].mean().reset_index()
    po["season"] += 1
    po = po.rename(columns={f: "po_" + f for f in FEATS})
    df = df.merge(me.drop(columns="size"), on=["player_id", "season"], how="left").merge(po, on=["season", "grp"], how="left")
    for f in FEATS:
        cum = g[f].cumsum() - df[f]
        mean_prev = (cum / df.n_prev.replace(0, np.nan)).fillna(0)
        prior = df["pl_" + f].fillna(df["po_" + f]).fillna(df.groupby("grp")[f].transform("mean"))
        df["pg_" + f] = (df.n_prev * mean_prev + k * prior) / (df.n_prev + k)
    return df.drop(columns=[c for c in df.columns if c.startswith(("pl_", "po_"))])
