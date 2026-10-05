import numpy as np
from helpers import stat_rows
from props import config as C
from props.defense import defense_ratings, shrink


def test_shrink():
    assert shrink(300, 3, 200, 6) == (3 * 300 + 6 * 200) / 9
    assert shrink(np.nan, 0, 200, 6) == 200
    assert shrink(300, 0, 200, 6) == 200
    assert shrink(300, 3, np.nan, 6) == 300             # rookie with no history: keep the sample mean
    assert np.isnan(shrink(np.nan, 0, np.nan, 6))


def test_rank_one_is_the_defense_allowing_the_most_yards():
    rows = []
    for wk in (1, 2, 3):
        for d, yds in (("AAA", 400), ("BBB", 250), ("CCC", 100)):
            rows.append(dict(player_id=f"qb_{d}_{wk}", position="QB", team="XXX", opponent_team=d,
                             week=wk, attempts=30, passing_yards=yds))
    stats = stat_rows(rows)
    r = defense_ratings(stats, stats.iloc[0:0], C.CATS["QB"]).set_index("defense")
    assert r.loc["AAA", "rank"] == 1
    assert r.loc["AAA", "rank"] < r.loc["BBB", "rank"] < r.loc["CCC", "rank"]
    assert r.loc["AAA", "cur_pg"] == 400 and r.loc["AAA", "games"] == 3
    assert r.loc["XXX", "games"] == 0                       # no games as a defense -> falls back to the prior
    assert r.loc["AAA", "factor"] > 1 > r.loc["CCC", "factor"]


def test_rb_ratings_only_count_running_backs():
    rows = [dict(player_id="rb", position="RB", team="XXX", opponent_team="AAA", week=1, carries=20, rushing_yards=100),
            dict(player_id="qb", position="QB", team="XXX", opponent_team="AAA", week=1, attempts=30, rushing_yards=60)]
    r = defense_ratings(stat_rows(rows), stat_rows(rows).iloc[0:0], C.CATS["RB"]).set_index("defense")
    assert r.loc["AAA", "cur_pg"] == 100
