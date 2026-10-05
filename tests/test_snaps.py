import pandas as pd
from props.snaps import prepare_snaps, recent_share

SNAP = pd.DataFrame({
    "pfr_player_id": ["A1", "A1", "A1", "A1", "B1", "C1", "A1"],
    "game_type": ["REG"] * 6 + ["POST"],
    "team": ["T"] * 7, "week": [1, 2, 3, 4, 1, 1, 5],
    "offense_snaps": [50, 60, 0, 70, 30, 10, 99],
    "offense_pct": [0.50, 0.60, 0.0, 0.70, 0.30, 0.10, 0.99]})
IDMAP = pd.DataFrame({"pfr_id": ["A1", "B1"], "gsis_id": ["g-a", "g-b"]})          # C1 has no gsis id


def test_prepare_snaps_maps_ids_and_drops_noise():
    s = prepare_snaps(SNAP, IDMAP)
    assert set(s.gsis_id) == {"g-a", "g-b"}                       # unmapped player dropped
    assert (s.offense_snaps > 0).all()                            # games he did not play are dropped
    assert 5 not in set(s.week)                                   # postseason row dropped
    assert prepare_snaps(None, None).empty and list(prepare_snaps(None, None).columns) == list(s.columns)


def test_recent_share_is_the_mean_of_the_last_three_games_played():
    s = prepare_snaps(SNAP, IDMAP)
    r = recent_share(s, "T", n=3)
    assert r["g-a"] == pytest.approx((0.50 + 0.60 + 0.70) / 3)
    assert r["g-b"] == pytest.approx(0.30)
    assert recent_share(s, "OTHER") == {}


import pytest  # noqa: E402  (kept below the helpers it is used by)
