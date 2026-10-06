import json

import pandas as pd
from props.scorecard import render, scorecard

COLS = ["player_id", "player_display_name", "position", "team", "season", "week", "attempts", "carries", "targets", "receptions",
        "passing_yards", "rushing_yards", "receiving_yards", "rushing_tds", "receiving_tds"]


def line(pid, pos, team, week, **kw):
    base = dict(player_id=pid, player_display_name=pid, position=pos, team=team, season=2026, week=week, attempts=0, carries=0,
                targets=0, receptions=0, passing_yards=0, rushing_yards=0, receiving_yards=0, rushing_tds=0, receiving_tds=0)
    return {**base, **kw}


def stats():
    return pd.DataFrame([
        line("qa1", "QB", "AAA", 4, attempts=30, passing_yards=250), line("qa1", "QB", "AAA", 5, attempts=10), line("qb2", "QB", "AAA", 5, attempts=25, passing_yards=200),
        line("qb1", "QB", "BBB", 4, attempts=30), line("qb1", "QB", "BBB", 5, attempts=0),
        line("rb1", "RB", "AAA", 5, carries=20, rushing_yards=90, rushing_tds=1),
        line("wr1", "WR", "AAA", 5, targets=8, receiving_yards=60),
        line("wr2", "WR", "BBB", 5, targets=8, receiving_yards=40, receiving_tds=1),
    ], columns=COLS)


def snap(built, td, elite=()):
    return {"season": 2026, "built": built, "td": list(td), "elite": list(elite), "backup": []}


def test_grades_latest_snapshot_and_skips_unplayed(tmp_path):
    d = tmp_path / "2026"
    d.mkdir()
    td = lambda pid, team, p: dict(week=5, pid=pid, team=team, pos="RB", p_td=p)
    (d / "2026-10-10T00-00-00Z.json").write_text(json.dumps(snap("a", [td("rb1", "AAA", 0.9), td("wr2", "BBB", 0.9)])))
    (d / "2026-10-11T00-00-00Z.json").write_text(json.dumps(snap("b", [td("rb1", "AAA", 0.5), td("wr2", "BBB", 0.1), td("ghost", "AAA", 0.3),
                                                                      td("rb9", "ZZZ", 0.2)])))
    elite = [dict(cat="WR", week=5, pid="wr1", team="AAA", proj=50.0, qb_flag=False, qb_p=0.0),
             dict(cat="WR", week=5, pid="wr2", team="BBB", proj=70.0, qb_flag=True, qb_p=0.6)]
    (d / "2026-10-12T00-00-00Z.json").write_text(json.dumps(snap("c", [], elite)))
    sc = scorecard(tmp_path, stats(), 2026)
    t = sc["td"]["all"]
    assert t["n"] == 2 and t["actual"] == 1.0 and t["predicted"] == 0.3              # latest numbers, ghost (DNP) and ZZZ (no game) dropped
    assert sc["yards"]["elite"]["WR"] == {"n": 2, "bias": -10.0, "mae": 20.0, "rmse": 22.4}
    q = sc["qb"]
    assert q["team_games_flagged"] == 1 and q["flagged_qb_missed"] == 1.0 and q["unflagged_qb_missed"] == 0.0
    assert "Scorecard 2026" in render(sc)


def test_nothing_to_grade(tmp_path):
    sc = scorecard(tmp_path, stats(), 2026)
    assert sc["weeks_graded"] == [] and "nothing to grade" in render(sc)
