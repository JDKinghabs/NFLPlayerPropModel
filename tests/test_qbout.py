import pandas as pd
import pytest
from helpers import stat_rows
from props import config as C
from props.elite import elite_table
from props.qbout import add_qb_flag, fresh_qb_risk, starter_qb

WR, RB, QB = C.CATS["WR"], C.CATS["RB"], C.CATS["QB"]


def team_stats(starter_weeks=(1, 2, 3), backup_weeks=()):
    """Team T: starter QB throws in `starter_weeks`; the backup in `backup_weeks`; a WR plays every week."""
    rows = []
    for wk in (1, 2, 3):
        rows.append(dict(player_id="qb1", player_display_name="Starter QB", position="QB", team="T", week=wk,
                         attempts=34 if wk in starter_weeks else 0))
        if wk in backup_weeks:
            rows.append(dict(player_id="qb2", player_display_name="Backup QB", position="QB", team="T", week=wk, attempts=30))
        rows.append(dict(player_id="wr1", player_display_name="Alpha", position="WR", team="T", week=wk, targets=9,
                         receiving_yards=90))
    return stat_rows(rows)


def pout(p=0.6, label="Q (60%)", pid="qb1"):
    return pd.DataFrame({"gsis_id": [pid], "p_out": [p], "label": [label], "stale": False, "source": "injury"})


def test_starter_is_the_attempts_leader_and_streak_counts_games_missed_in_a_row():
    pid, name, streak = starter_qb(team_stats(), "T", 4)
    assert (pid, name, streak) == ("qb1", "Starter QB", 0)
    pid, _, streak = starter_qb(team_stats(starter_weeks=(1, 2), backup_weeks=(3,)), "T", 4)
    assert pid == "qb1" and streak == 1                        # still the starter by attempts, but missed last game
    assert starter_qb(team_stats(starter_weeks=()), "T", 4) is None
    assert starter_qb(team_stats(), "T", 1) is None            # nothing before week 1


def test_only_a_first_missed_game_is_news():
    st = team_stats()
    name, p, label = fresh_qb_risk(st, pout(), "T", 4)
    assert (name, p, label) == ("Starter QB", 0.6, "Q (60%)")
    long_absence = team_stats(starter_weeks=(1, 2), backup_weeks=(3,))
    assert fresh_qb_risk(long_absence, pout(1.0, "OUT"), "T", 4) is None        # already in the season averages
    assert fresh_qb_risk(st, pout(pid="someone_else"), "T", 4) is None          # QB not on the report
    assert fresh_qb_risk(st, pd.DataFrame(columns=["gsis_id", "p_out", "label"]), "T", 4) is None
    assert fresh_qb_risk(st, None, "T", 4) is None


def rows_for(team="T", week=4, proj=80.0):
    return pd.DataFrame({"team": [team], "week": [week], "proj": [proj]})


def test_flag_applies_the_historical_effect_to_a_what_if_number_and_only_for_wr():
    st = team_stats()
    r = add_qb_flag(rows_for(), WR, st, {4: pout()}).iloc[0]
    assert r.q_flag and r.q_p == 0.6 and r.q_txt == "Starter QB Q (60%)"
    assert r.q_if == pytest.approx(80.0 * (1 + C.QB_OUT_EFFECT["WR"]["yards"]))
    for cat in (RB, QB):                                        # no validated effect for these
        assert not add_qb_flag(rows_for(), cat, st, {4: pout()}).iloc[0].q_flag
    quiet = add_qb_flag(rows_for(), WR, st, {4: pout(pid="x")}).iloc[0]
    assert not quiet.q_flag and quiet.q_txt == "" and pd.isna(quiet.q_p) and pd.isna(quiet.q_if)


def test_empty_frames_keep_the_columns():
    out = add_qb_flag(pd.DataFrame({"team": [], "week": [], "proj": []}), WR, team_stats(), {})
    assert {"q_flag", "q_txt", "q_p", "q_if"} <= set(out.columns) and out.empty


def test_elite_table_carries_the_flag_for_wrs_on_a_team_with_a_questionable_qb():
    rows = []
    for i, t in enumerate(["T", "U", "V"]):
        for wk in (1, 2, 3):
            rows.append(dict(player_id=f"wr{i}", player_display_name=f"WR {i}", position="WR", team=t, week=wk,
                             opponent_team="DDD", targets=8, receiving_yards=100 - 5 * i))
            rows.append(dict(player_id=f"qb{i}", player_display_name=f"QB {i}", position="QB", team=t, week=wk,
                             opponent_team="DDD", attempts=33))
    stats = stat_rows(rows)
    ratings = pd.DataFrame({"defense": ["DDD"], "rank": [1], "blend": [170.0], "vs_lg": [0.15], "factor": [1.15]})
    slate = pd.DataFrame({"game_id": "g", "week": 4, "kickoff": pd.Timestamp("2026-10-11 13:00", tz="America/New_York"),
                          "team": ["T", "U", "V"], "opp": "DDD", "home": False, "spread": 3.0, "ou": 45.0})
    t = elite_table(WR, stats, stats.iloc[0:0], ratings, slate, {4: pout(0.6, "Q (60%)", "qb0")}).set_index("team")
    assert bool(t.loc["T", "q_flag"]) and not t.loc["U", "q_flag"] and not t.loc["V", "q_flag"]
    assert t.loc["T", "q_if"] == pytest.approx(t.loc["T", "proj"] * (1 + C.QB_OUT_EFFECT["WR"]["yards"]))
    assert t.loc["T", "proj"] > 0                                # the headline projection itself is untouched
