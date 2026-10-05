import numpy as np
import pandas as pd
import pytest
from helpers import stat_rows
from props import config as C
from props.defense import matchup_beta
from props.elite import elite_table

WR = C.CATS["WR"]


def test_matchup_beta_falls_with_rank():
    assert matchup_beta("QB", 1) == matchup_beta("QB", 10) == 0.75
    assert matchup_beta("RB", 5) == 0.60 and matchup_beta("RB", 12) == 0.30
    assert matchup_beta("WR", 10) == 0.45 and matchup_beta("WR", 11) == 0.0 and matchup_beta("WR", 25) == 0.0


def test_pools_are_sized_per_position():
    assert {k: c.elite_n for k, c in C.CATS.items()} == {"QB": 10, "RB": 15, "WR": 25}


def make(n_players=30):
    rows, teams = [], [f"T{i:02d}" for i in range(n_players)]
    for i, t in enumerate(teams):
        for wk in (1, 2, 3):
            rows.append(dict(player_id=f"wr{i}", player_display_name=f"WR {i}", position="WR", team=t, week=wk,
                             opponent_team="DDD", targets=8, receiving_yards=120 - 3 * i))
    stats = stat_rows(rows)
    ratings = pd.DataFrame({"defense": ["DDD"], "rank": [1], "blend": [170.0], "vs_lg": [0.15], "factor": [1.15]})
    slate = pd.DataFrame({"game_id": "g", "week": 4, "kickoff": pd.Timestamp("2026-10-11 13:00", tz="America/New_York"),
                          "team": teams, "opp": "DDD", "home": False, "spread": 3.0, "ou": 45.0})
    return stats, ratings, slate


def test_wr_pool_is_top_25_and_depth_receivers_get_no_matchup_boost():
    stats, ratings, slate = make()
    t = elite_table(WR, stats, stats.iloc[0:0], ratings, slate, {4: pd.DataFrame(columns=["gsis_id", "p_out", "label", "stale"])})
    assert len(t) == 25 and t["rank"].max() == 25
    top, depth = t[t["rank"] == 1].iloc[0], t[t["rank"] == 20].iloc[0]
    assert top.beta == 0.45 and depth.beta == 0.0
    assert top.proj > top.base                                   # boosted by the weak defense
    assert depth.proj == pytest.approx(depth.base)               # tier with no demonstrated matchup signal


def test_rookie_without_last_season_still_gets_a_projection():
    stats, ratings, slate = make()
    t = elite_table(WR, stats, stats.iloc[0:0], ratings, slate, {4: pd.DataFrame(columns=["gsis_id", "p_out", "label", "stale"])})
    assert t.proj.notna().all() and not np.isnan(t.base).any()
