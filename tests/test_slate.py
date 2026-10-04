import pandas as pd
from props.slate import ET, fmt_kick, fmt_spread_total, select_slate


def games():
    return pd.DataFrame([
        dict(game_id="a", season=2026, game_type="REG", week=4, gameday="2026-10-04", gametime="13:00",
             home_team="MIN", away_team="MIA", home_score=None, away_score=None, spread_line=10.0, total_line=38.5),
        dict(game_id="b", season=2026, game_type="REG", week=4, gameday="2026-10-04", gametime="20:20",
             home_team="CAR", away_team="DET", home_score=None, away_score=None, spread_line=-3.5, total_line=51.5),
        dict(game_id="c", season=2026, game_type="REG", week=4, gameday="2026-10-01", gametime="20:15",
             home_team="CLE", away_team="PIT", home_score=27, away_score=24, spread_line=3.0, total_line=40.0),
        dict(game_id="d", season=2026, game_type="REG", week=5, gameday="2026-10-11", gametime="13:00",
             home_team="NE", away_team="LV", home_score=None, away_score=None, spread_line=3.5, total_line=44.5),
    ])


NOW = pd.Timestamp("2026-10-04 18:00", tz=ET)


def test_auto_week_keeps_only_unstarted_unplayed_games():
    s = select_slate(games(), 2026, None, now=NOW)
    assert set(s.game_id) == {"b"}                 # 'a' already kicked off, 'c' is final, 'd' is next week
    assert set(s.week) == {4}


def test_explicit_weeks_and_include_started():
    assert set(select_slate(games(), 2026, [4, 5], now=NOW).game_id) == {"b", "d"}
    assert set(select_slate(games(), 2026, [4], now=NOW, include_started=True).game_id) == {"a", "b"}


def test_spread_sign_is_bookmaker_notation_per_team():
    s = select_slate(games(), 2026, [4, 5], now=NOW, include_started=True).set_index(["game_id", "team"])
    # spread_line > 0 => home favoured by that much
    assert s.loc[("a", "MIN"), "spread"] == -10.0 and s.loc[("a", "MIA"), "spread"] == 10.0
    # spread_line < 0 => away favoured
    assert s.loc[("b", "CAR"), "spread"] == 3.5 and s.loc[("b", "DET"), "spread"] == -3.5
    assert bool(s.loc[("a", "MIN"), "home"]) and not bool(s.loc[("a", "MIA"), "home"])


def test_formatting():
    assert fmt_spread_total(-10.0, 38.5) == "-10 / 38.5"
    assert fmt_spread_total(3.5, 51.5) == "+3.5 / 51.5"
    assert fmt_spread_total(float("nan"), 40) == ""
    assert fmt_kick(pd.Timestamp("2026-10-04 16:25", tz=ET)) == "Sun 10/4 4:25p"
    assert fmt_kick(pd.Timestamp("2026-10-11 09:30", tz=ET)) == "Sun 10/11 9:30a"
