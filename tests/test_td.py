import numpy as np
import pandas as pd
import pytest
from helpers import stat_rows
from props import config as C
from props import td as TD

KICK = pd.Timestamp("2026-10-11 13:00", tz="America/New_York")


def test_buckets_follow_the_yard_line_edges():
    y = [1, 2, 3, 4, 5, 6, 9, 12, 13, 20, 21, 35, 36, 50, 51, 99]
    assert TD.bucket(y).tolist() == [0, 1, 2, 3, 3, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9]


def pbp_rows(rows):
    base = dict(season=2026, week=1, season_type="REG", posteam="T", play_type="run", yardline_100=50, rusher_player_id=None,
                receiver_player_id=None, rush_touchdown=0, pass_touchdown=0, sack=0, two_point_attempt=0)
    return pd.DataFrame([{**base, **r} for r in rows])


def test_clean_pbp_keeps_regular_season_rushes_and_targets_only():
    d = pbp_rows([dict(rusher_player_id="a"), dict(play_type="pass", receiver_player_id="b"),
                  dict(play_type="pass"),                                       # no receiver: a throwaway or a sack
                  dict(rusher_player_id="a", season_type="POST"), dict(rusher_player_id="a", two_point_attempt=1),
                  dict(rusher_player_id="a", yardline_100=None)])
    assert len(TD.clean_pbp(d)) == 2


def test_td_rates_are_the_share_of_plays_in_each_bucket_that_scored():
    d = TD.clean_pbp(pbp_rows([dict(rusher_player_id="a", yardline_100=1, rush_touchdown=int(i < 6)) for i in range(10)]
                              + [dict(play_type="pass", receiver_player_id="b", yardline_100=8, pass_touchdown=int(i < 1)) for i in range(4)]))
    rr, rt = TD.td_rates([d])
    assert rr[0] == pytest.approx(0.6) and rr[1:].sum() == 0
    assert rt[4] == pytest.approx(0.25)


def test_player_weeks_sums_expected_tds_and_red_zone_usage():
    d = TD.clean_pbp(pbp_rows([dict(rusher_player_id="a", yardline_100=1), dict(rusher_player_id="a", yardline_100=40),
                               dict(play_type="pass", receiver_player_id="a", yardline_100=8),
                               dict(play_type="pass", receiver_player_id="b", yardline_100=15)]))
    rr, rt = np.linspace(0.5, 0.0, 10), np.linspace(0.4, 0.0, 10)
    pw = TD.player_weeks(d, rr, rt).set_index("player_id")
    a = pw.loc["a"]
    assert a.rush_xtd == pytest.approx(rr[0] + rr[8]) and a.rush10 == 1 and a.rush5 == 1
    assert a.tgt_xtd == pytest.approx(rt[4]) and a.tgt10 == 1 and a.tgt20 == 1
    assert pw.loc["b"].rush_xtd == 0 and pw.loc["b"].tgt20 == 1 and pw.loc["b"].tgt10 == 0
    assert TD.player_weeks(None, rr, rt).empty


def test_pregame_shrinks_this_seasons_games_toward_last_season():
    rows = []
    for wk in range(1, 11):                                                    # last season: scored in 5 of 10 games
        rows.append(dict(player_id="p", season=2025, week=wk, grp="WR", td=int(wk <= 5)))
    for wk in (1, 2):                                                          # this season so far: no TDs
        rows.append(dict(player_id="p", season=2026, week=wk, grp="WR", td=0))
    rows.append(dict(player_id="p", season=2026, week=99, grp="WR", td=0))      # the upcoming game
    d = pd.DataFrame(rows)
    for f in TD.FEATS:
        if f not in d:
            d[f] = 0.0
    out = TD.pregame(d)
    nxt = out[(out.season == 2026) & (out.week == 99)].iloc[0]
    assert nxt.n_prev == 2
    assert nxt.pg_td == pytest.approx((2 * 0.0 + C.PLAYER_PRIOR_GAMES * 0.5) / (2 + C.PLAYER_PRIOR_GAMES))


def test_fair_odds_and_predict():
    assert TD.fair_odds(0.5) == "-100" and TD.fair_odds(0.6) == "-150" and TD.fair_odds(0.25) == "+300"
    assert TD.fair_odds(0.0) == "" and TD.fair_odds(1.0) == ""
    gm = {"features": ["a", "b"], "mean": [1.0, 0.0], "sd": [2.0, 1.0], "coef": [-1.0, 0.5, 2.0]}
    p = TD.predict(gm, pd.DataFrame({"a": [3.0], "b": [0.25]}))
    assert p[0] == pytest.approx(1 / (1 + np.exp(-(-1.0 + 0.5 * 1.0 + 2.0 * 0.25))))


def toy_model():
    g = {"features": TD.MODEL_FEATURES, "mean": [0.0] * 5, "sd": [1.0] * 5, "coef": [-1.0] + [0.2] * 5, "n": 1, "td_rate": 0.2}
    return {"version": "test", "rush_rate": np.linspace(0.5, 0, 10).tolist(), "tgt_rate": np.linspace(0.4, 0, 10).tolist(),
            "tt_mean": 22.0, "groups": {"RB": g, "WR": g, "TE": g}}


def slate(ou=47.0, spread=-7.0):
    return pd.DataFrame({"game_id": "g", "week": 4, "kickoff": KICK, "team": ["T", "U"], "opp": ["U", "T"], "home": [True, False],
                         "spread": [spread, -spread], "ou": ou})


def world():
    """Team T: RB1 (18 touches), RB2 (3: below the role threshold), WR1, a Questionable WR, a WR ruled out, TE, QB; plus a
    rookie with no history; team U has one WR."""
    rows = []
    for wk in (1, 2, 3):
        for pid, pos, car, tg, rtd in [("rb1", "RB", 15, 3, int(wk == 1)), ("rb2", "RB", 3, 0, 0), ("wr1", "WR", 0, 9, 0),
                                       ("wrq", "WR", 0, 7, 0), ("wro", "WR", 0, 8, 0), ("te1", "TE", 0, 5, 0)]:
            rows.append(dict(player_id=pid, player_display_name=pid.upper(), position=pos, team="T", week=wk, carries=car,
                             targets=tg, rushing_tds=rtd))
        rows.append(dict(player_id="qb1", player_display_name="QB1", position="QB", team="T", week=wk, attempts=30))
        rows.append(dict(player_id="wu", player_display_name="WU", position="WR", team="U", week=wk, targets=9))
    stats = stat_rows(rows)
    ros = pd.DataFrame([dict(team="T" if p != "wu" else "U", position=pos, full_name=p.upper(), gsis_id=p, status="ACT", week=3)
                        for p, pos in [("rb1", "RB"), ("rb2", "RB"), ("wr1", "WR"), ("wrq", "WR"), ("wro", "WR"), ("te1", "TE"),
                                       ("qb1", "QB"), ("wu", "WR"), ("rookie", "WR")]])
    pbp = TD.clean_pbp(pbp_rows([dict(rusher_player_id="rb1", yardline_100=1, rush_touchdown=1),
                                 dict(play_type="pass", receiver_player_id="wr1", yardline_100=8)]))
    po = pd.DataFrame({"gsis_id": ["wro", "wrq"], "p_out": [1.0, 0.28], "label": ["OUT", "Q (28%)"], "stale": False, "source": "injury"})
    # last season: RB2 was a 2-touch backup for a full year, so this season's 3 touches a game do not make him a role player
    prev = stat_rows([dict(player_id="rb2", player_display_name="RB2", position="RB", team="T", week=w, season=2025, carries=2)
                      for w in range(1, 13)])
    return stats, pbp, ros, po, prev


def table(**kw):
    stats, pbp, ros, po, prev = world()
    args = dict(stats=stats, prev_stats=prev, pbp=pbp, prev_pbp=pbp.iloc[0:0], roster=ros, slate=slate(),
                pout_by_week={4: po}, model=toy_model())
    args.update(kw)
    return TD.td_table(**args)


def test_td_table_lists_role_players_ranked_within_position():
    t = table()
    assert set(t) == {"RB", "WR", "TE"}                                           # QBs are not modelled
    assert t["RB"].name.tolist() == ["RB1"]                                       # RB2 is below the role threshold
    wr = t["WR"]
    assert set(wr.name) == {"WR1", "WRQ", "WU"}                                   # ruled-out WR and the rookie with no history are gone
    assert wr["rank"].tolist() == [1, 2, 3] and wr.p_td.is_monotonic_decreasing
    assert wr.set_index("name").loc["WRQ", "inj"] == "Q (28%)" and wr.set_index("name").loc["WR1", "inj"] == ""
    assert t["TE"].name.tolist() == ["TE1"]
    allp = pd.concat(t.values())
    assert allp.p_td.between(0.01, 0.99).all() and allp.fair.str.match(r"^[+-]\d+$").all()


def test_team_total_comes_from_the_market_and_falls_back_when_there_is_no_line():
    t = table()["WR"].set_index("name")
    assert t.loc["WR1", "tt"] == pytest.approx(27.0) and t.loc["WU", "tt"] == pytest.approx(20.0)     # 47/2 -/+ 3.5
    no_line = table(slate=slate(ou=np.nan, spread=np.nan))["WR"].set_index("name")
    assert no_line.tt.isna().all() and no_line.p_td.notna().all()
    assert t.loc["WR1", "p_td"] > no_line.loc["WR1", "p_td"] > t.loc["WU", "p_td"] - 1               # market info moves the number


def test_a_backup_whose_starter_is_out_is_flagged_not_rescored():
    base = table()["WR"].set_index("name")
    flagged = table(backup_ids={"wr1"})["WR"].set_index("name")
    assert flagged.loc["WR1", "role_up"] and "role may be bigger" in flagged.loc["WR1", "note"]
    assert flagged.loc["WR1", "p_td"] == pytest.approx(base.loc["WR1", "p_td"])                       # information only


def test_returning_player_with_only_last_season_history_is_included():
    stats, pbp, ros, po, prev = world()
    back = stat_rows([dict(player_id="back", player_display_name="BACK", position="WR", team="T", week=w, season=2025, targets=8)
                      for w in range(1, 13)])
    ros = pd.concat([ros, pd.DataFrame([dict(team="T", position="WR", full_name="BACK", gsis_id="back", status="ACT", week=3)])])
    wr = table(roster=ros, prev_stats=pd.concat([prev, back]))["WR"]
    assert "BACK" in set(wr.name)                                                 # no games this season, but a full last season


def test_missing_inputs_degrade_to_empty_tables_instead_of_breaking():
    assert all(len(v) == 0 for v in table(model=None).values())
    assert all(len(v) == 0 for v in table(slate=slate().iloc[0:0]).values())
    assert all(len(v) == 0 for v in table(roster=pd.DataFrame()).values())
    no_pbp = table(pbp=TD.read_pbp(None), prev_pbp=TD.read_pbp(None))              # play-by-play failed to download: still rank by usage
    assert len(no_pbp["WR"]) == 3 and no_pbp["WR"].p_td.notna().all()
    assert len(table(prev_pbp=TD.read_pbp(None))["RB"]) == 1                      # last season's play-by-play missing but its stats present
