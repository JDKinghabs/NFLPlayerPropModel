from helpers import stat_rows
from props.results import build_results


def test_results_keys_and_positions():
    stats = stat_rows([
        dict(player_id="qb1", position="QB", team="AAA", week=3, attempts=30, passing_yards=250),
        dict(player_id="rb1", position="RB", team="AAA", week=3, carries=20, receptions=3, rushing_yards=88),
        dict(player_id="te1", position="TE", team="AAA", week=3, targets=5, receiving_yards=40),     # not a prop category
        dict(player_id="wr1", position="WR", team="BBB", week=3, targets=8, receiving_yards=0),      # active, zero yards
        dict(player_id="wr1", position="WR", team="BBB", week=4, targets=8, receiving_yards=100),
    ])
    r = build_results(stats, 2026)
    assert r["final"] == ["2026|3|AAA", "2026|3|BBB", "2026|4|BBB"]
    assert r["y"] == {"2026|3|qb1|QB": 250, "2026|3|rb1|RB": 88, "2026|3|wr1|WR": 0, "2026|4|wr1|WR": 100}
    # touches: QB attempts, RB carries + catches, WR targets
    assert r["t"] == {"2026|3|qb1|QB": 30, "2026|3|rb1|RB": 23, "2026|3|wr1|WR": 8, "2026|4|wr1|WR": 8}


def test_results_empty_stats():
    import pandas as pd
    assert build_results(pd.DataFrame(), 2026) == {"season": 2026, "final": [], "y": {}, "t": {}}
