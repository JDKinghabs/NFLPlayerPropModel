import pandas as pd
import pytest
from helpers import stat_rows
from props import config as C
from props.backups import _scenario, _TeamVolume, backup_table
from props.defense import defense_ratings

RB = C.CATS["RB"]


def team_volume(per_week):
    """per_week: {week: {player: carries}} for team T."""
    rows = [dict(player_id=p, position="QB" if p == "q" else "RB", team="T", week=w, carries=c)
            for w, d in per_week.items() for p, c in d.items()]
    return _TeamVolume(stat_rows(rows), "carries")


def test_vacated_share_goes_to_the_backup():
    tv = team_volume({w: {"r1": 20, "r2": 5, "q": 3} for w in (1, 2, 3)})
    shares, n_with, n_wo = _scenario(tv, RB, ["r1"], ["r2"], {"r2": 2})
    assert (n_with, n_wo) == (3, 0)
    assert shares["r2"] == pytest.approx(5 / 28 + 20 / 28)        # whole vacated share, group of one


def test_no_injury_returns_season_share():
    tv = team_volume({w: {"r1": 20, "r2": 5, "q": 3} for w in (1, 2)})
    shares, _, _ = _scenario(tv, RB, [], ["r1", "r2"], {})
    assert shares["r1"] == pytest.approx(20 / 28) and shares["r2"] == pytest.approx(5 / 28)


def test_role_already_established_is_not_double_counted():
    # r1 played weeks 1-2, missed 3-4; r2 already took 20/28 of volume in the games without him
    tv = team_volume({1: {"r1": 20, "r2": 5, "q": 3}, 2: {"r1": 20, "r2": 5, "q": 3},
                      3: {"r2": 20, "q": 8}, 4: {"r2": 20, "q": 8}})
    shares, n_with, n_wo = _scenario(tv, RB, ["r1"], ["r2"], {"r2": 2})
    assert (n_with, n_wo) == (2, 2)
    lam = 2 / (2 + C.WITHOUT_SAMPLE_PRIOR)
    assert shares["r2"] == pytest.approx(lam * (40 / 56) + (1 - lam) * (5 / 28 + 20 / 28))
    assert 40 / 56 < shares["r2"] < 25 / 28


def test_starter_who_never_played_leaves_actual_usage_untouched():
    tv = team_volume({w: {"r2": 20, "q": 8} for w in (1, 2, 3)})
    tv.mat["r1"] = 0.0
    shares, n_with, n_wo = _scenario(tv, RB, ["r1"], ["r2"], {"r2": 2})
    assert n_with == 0 and shares["r2"] == pytest.approx(20 / 28)


def build_team(r1_status):
    rows = []
    for w in (1, 2, 3):
        for opp in ("OPP",):
            rows += [dict(player_id="r1", player_display_name="Starter", position="RB", team="T", opponent_team=opp,
                          week=w, carries=20, rushing_yards=90),
                     dict(player_id="r2", player_display_name="Backup", position="RB", team="T", opponent_team=opp,
                          week=w, carries=5, rushing_yards=20),
                     dict(player_id="q", position="QB", team="T", opponent_team=opp, week=w, carries=3, rushing_yards=15)]
    stats = stat_rows(rows)
    ratings = defense_ratings(stats, stats.iloc[0:0], RB)
    slate = pd.DataFrame([dict(game_id="g", week=4, kickoff=pd.Timestamp("2026-10-11 13:00", tz="America/New_York"),
                               team="T", opp="OPP", home=True, spread=-3.0, ou=44.0)])
    depth = pd.DataFrame({"team": ["T", "T"], "gsis_id": ["r1", "r2"], "pos_abb": ["RB", "RB"], "pos_rank": [1, 2],
                          "player_name": ["Starter", "Backup"]})
    roster = pd.DataFrame({"team": ["T", "T"], "position": ["RB", "RB"], "full_name": ["Starter", "Backup"],
                           "gsis_id": ["r1", "r2"], "status": ["ACT", "ACT"], "week": [4, 4]})
    pout = pd.DataFrame({"gsis_id": ["r1"], "p_out": [r1_status], "label": ["OUT"], "stale": [False]})
    return backup_table(RB, stats, stats.iloc[0:0], ratings, slate, depth, roster, {4: pout}, None)


def test_backup_table_lists_backup_when_starter_is_out():
    t = build_team(1.0)
    assert list(t.name) == ["Backup"]
    row = t.iloc[0]
    assert row.p_out == 1.0 and row.role == "RB2" and "Starter" in row.starters_out
    assert row.proj_vol > row.base_vol > 0
    assert row.proj_exp == pytest.approx(row.proj_if_out)


def test_questionable_starter_gives_probability_weighted_projection():
    row = build_team(0.28).iloc[0]
    assert row.p_out == pytest.approx(0.28)
    assert row.proj_exp < row.proj_if_out


def test_nothing_listed_when_everyone_healthy():
    assert build_team(0.0).empty
