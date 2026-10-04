import pandas as pd
from helpers import stat_rows
from props.availability import p_out_table


def inj(rows):
    base = dict(season=2026, season_type="REG", game_type="REG", position="WR", report_status=None,
                practice_status="Full Participation in Practice")
    return pd.DataFrame([{**base, **r} for r in rows])


ROSTER = pd.DataFrame({"team": ["T1", "T1"], "position": ["WR", "RB"], "full_name": ["A", "B"],
                       "gsis_id": ["ir", "game_day_inactive"], "status": ["RES", "INA"], "week": [4, 4]})


def p(table, gid):
    row = table[table.gsis_id == gid]
    return None if row.empty else float(row.p_out.iloc[0])


def test_same_week_report():
    i = inj([dict(team="T1", week=4, gsis_id="o", report_status="Out"),
             dict(team="T1", week=4, gsis_id="d", report_status="Doubtful"),
             dict(team="T1", week=4, gsis_id="qwr", report_status="Questionable"),
             dict(team="T1", week=4, gsis_id="qqb", report_status="Questionable", position="QB"),
             dict(team="T1", week=4, gsis_id="dnp", practice_status="Did Not Participate In Practice"),
             dict(team="T1", week=4, gsis_id="ok")])
    t = p_out_table(i, ROSTER, 4)
    assert p(t, "o") == 1.0 and p(t, "d") == 1.0
    assert p(t, "qwr") == 0.28 and p(t, "qqb") == 0.60 and p(t, "dnp") == 0.27
    assert p(t, "ok") is None
    assert not t.stale.any()


def test_roster_ir_is_certain_but_game_day_inactive_is_ignored():
    t = p_out_table(inj([]), ROSTER, 4)
    assert p(t, "ir") == 1.0
    assert p(t, "game_day_inactive") is None       # INA is last week's game-day list, not durable


def test_stale_report_carries_forward_at_calibrated_odds():
    i = inj([dict(team="T1", week=4, gsis_id="o", report_status="Out"),
             dict(team="T1", week=4, gsis_id="d", report_status="Doubtful"),
             dict(team="T1", week=4, gsis_id="q_sat", report_status="Questionable"),
             dict(team="T1", week=4, gsis_id="q_played", report_status="Questionable"),
             dict(team="T2", week=4, gsis_id="q_notyet", report_status="Questionable")])
    # week-4 stats: q_played had volume, q_sat did not; T2 has not played week 4 yet
    stats = stat_rows([dict(player_id="q_played", position="WR", team="T1", week=4, targets=5),
                       dict(player_id="someone_else", position="WR", team="T1", week=4, targets=3)])
    t = p_out_table(i, ROSTER, 5, stats)
    assert t.stale[t.gsis_id == "o"].iloc[0]
    assert p(t, "o") == 0.67 and p(t, "d") == 0.62
    assert p(t, "q_sat") == 0.52
    assert p(t, "q_played") is None
    assert p(t, "q_notyet") is None                # his game hasn't happened, so "sat" is unknown
