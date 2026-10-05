import numpy as np
import pandas as pd
import pytest
from helpers import stat_rows
from props import config as C
from props.defense import defense_ratings
from props.touches import add_outlook, player_touches, vacated_share
from props.volume import touch_col

QB, RB, WR = C.CATS["QB"], C.CATS["RB"], C.CATS["WR"]


def test_touch_definition_per_position():
    d = pd.DataFrame({"attempts": [30], "carries": [18], "receptions": [4], "targets": [7]})
    assert touch_col(d, "QB").iloc[0] == 30 and touch_col(d, "RB").iloc[0] == 22 and touch_col(d, "WR").iloc[0] == 7
    assert touch_col(d.drop(columns="receptions"), "RB").iloc[0] == 18        # old data without a receptions column


def test_volume_factor_ranks_defenses_by_attempts_faced():
    rows = []
    for wk in (1, 2, 3):
        for d, att in (("AAA", 45), ("BBB", 33), ("CCC", 21)):
            rows.append(dict(player_id=f"qb_{d}_{wk}", position="QB", team="XXX", opponent_team=d, week=wk,
                             attempts=att, passing_yards=att * 7))
    stats = stat_rows(rows)
    r = defense_ratings(stats, stats.iloc[0:0], QB).set_index("defense")
    assert r.loc["AAA", "vol_factor"] > r.loc["BBB", "vol_factor"] > r.loc["CCC", "vol_factor"]
    assert r.vol_factor.mean() == pytest.approx(1.0)


def test_player_touches_baseline_shrinks_toward_last_season():
    cur = stat_rows([dict(player_id="p", position="WR", team="T", week=w, targets=12, receiving_yards=100) for w in (1, 2, 3)])
    prev = stat_rows([dict(player_id="p", position="WR", team="T", week=w, targets=6, receiving_yards=50, season=2025) for w in range(1, 11)])
    t = player_touches(cur, prev, WR).iloc[0]
    assert t.t_cur == 12 and t.t_l3 == 12
    assert t.t_base == pytest.approx((3 * 12 + C.PLAYER_PRIOR_GAMES * 6) / (3 + C.PLAYER_PRIOR_GAMES))
    rookie = player_touches(cur, cur.iloc[0:0], WR).iloc[0]
    assert rookie.t_base == 12                                              # no history: keep this season's average


def team_stats():
    rows = []
    for wk in (1, 2, 3):
        rows += [dict(player_id="rb1", player_display_name="Starter", position="RB", team="T", week=wk, carries=18, receptions=4, targets=5),
                 dict(player_id="rb2", player_display_name="Change", position="RB", team="T", week=wk, carries=8, receptions=2, targets=3),
                 dict(player_id="wr1", player_display_name="Alpha", position="WR", team="T", week=wk, targets=10),
                 dict(player_id="wr2", player_display_name="Beta", position="WR", team="T", week=wk, targets=6),
                 dict(player_id="te1", player_display_name="Tight", position="TE", team="T", week=wk, targets=4)]
    return stat_rows(rows)


def test_vacated_share_is_probability_weighted_and_pool_specific():
    st = team_stats()
    v, items = vacated_share(st, "RB", "T", {"rb1": 1.0}, exclude="rb2")
    assert v == pytest.approx(22 / 32) and items[0][1] == "Starter"            # RB pool = RB/FB carries + catches
    v, _ = vacated_share(st, "WR", "T", {"wr2": 0.5, "te1": 1.0}, exclude="wr1")   # WR pool = every teammate's targets
    assert v == pytest.approx(0.5 * 6 / 28 + 1.0 * 4 / 28)        # pool = all 28 team targets, RBs included
    assert vacated_share(st, "WR", "T", {"wr1": 1.0}, exclude="wr1")[0] == 0.0   # the player himself never counts
    assert vacated_share(st, "QB", "T", {"rb1": 1.0})[0] == 0.0                  # QBs have no workload flag


def outlook_for(cat, pid, absent_label, fvol=1.0):
    st = team_stats()
    m = pd.DataFrame({"player_id": [pid], "team": ["T"], "opp": ["DDD"], "week": [4]})
    ratings = pd.DataFrame({"defense": ["DDD"], "vol_factor": [fvol]})
    po = pd.DataFrame({"gsis_id": list(absent_label), "p_out": [x[0] for x in absent_label.values()],
                       "label": [x[1] for x in absent_label.values()], "stale": False, "source": "injury"})
    return add_outlook(m, cat, st, st.iloc[0:0], ratings, {4: po}).iloc[0]


def test_qb_expectation_moves_with_attempts_faced_but_workload_flag_never_changes_rb_wr_number():
    st = team_stats().assign(attempts=0)
    st.loc[st.player_id == "wr1", "position"] = "QB"; st.loc[st.player_id == "wr1", "attempts"] = 30
    m = pd.DataFrame({"player_id": ["wr1"], "team": ["T"], "opp": ["DDD"], "week": [4]})
    hi = add_outlook(m, QB, st, st.iloc[0:0], pd.DataFrame({"defense": ["DDD"], "vol_factor": [1.20]}), {}).iloc[0]
    lo = add_outlook(m, QB, st, st.iloc[0:0], pd.DataFrame({"defense": ["DDD"], "vol_factor": [0.90]}), {}).iloc[0]
    assert hi.t_exp == pytest.approx(30 * (1 + C.TOUCH_QB_VOLUME_BETA * 0.20)) and lo.t_exp < lo.t_base < hi.t_exp
    r = outlook_for(RB, "rb2", {"rb1": (1.0, "OUT")})
    assert r.t_flag and r.t_if > r.t_base and r.t_exp == r.t_base                  # flag + "if the bump holds"; headline unchanged
    assert "Starter OUT" in r.t_out and r.t_vac == pytest.approx(22 / 32)
    w = outlook_for(WR, "wr1", {"te1": (0.28, "Q (28%)")})
    assert w.t_vac == pytest.approx(0.28 * 4 / 28) and not w.t_flag              # 4% expected vacated: under the 5% flag threshold
