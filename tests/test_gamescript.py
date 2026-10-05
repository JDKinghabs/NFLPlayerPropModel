import math

import pytest
from props import config as C
from props.gamescript import context_effect, multiplier

QB = C.GAME_SCRIPT["QB"]


def test_only_qbs_are_adjusted():
    assert multiplier("RB", -7, 50, True) == 1.0 and multiplier("WR", -7, 50, True) == 1.0
    assert context_effect("WR", -7, 50, True) == 0.0


def test_higher_implied_total_and_home_field_raise_the_qb_projection():
    low = multiplier("QB", +3, 38.0, False)           # underdog in a low-scoring game, on the road
    mid = multiplier("QB", 0, 44.0, True)
    high = multiplier("QB", -7, 52.0, True)           # big favourite in a shootout, at home
    assert low < mid < high
    assert multiplier("QB", -3, 47, True) > multiplier("QB", -3, 47, False)


def test_implied_team_total_uses_spread_sign_convention():
    # spread < 0 means the team is favoured: team total = total/2 + margin/2
    fav = context_effect("QB", -6.0, 46.0, False)
    dog = context_effect("QB", +6.0, 46.0, False)
    assert fav > dog
    expect = QB["tt"] * ((46 / 2 + 6 / 2) / C.LEAGUE_TEAM_TOTAL - 1 - QB["tt_ref"]) + QB["home"] * (0 - 0.5)
    assert fav == pytest.approx(expect)


def test_missing_line_falls_back_to_a_typical_game_and_level_is_optional():
    no_line = multiplier("QB", math.nan, math.nan, True)
    assert no_line == pytest.approx(1 + QB["level"] + QB["home"] * 0.5)
    assert multiplier("QB", -3, 47, True, level=False) == pytest.approx(multiplier("QB", -3, 47, True) - QB["level"])
