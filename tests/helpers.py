import pandas as pd

STAT_COLS = ["player_id", "player_display_name", "position", "team", "opponent_team", "season", "week",
             "season_type", "attempts", "carries", "targets", "passing_yards", "rushing_yards",
             "receiving_yards"]


def stat_rows(rows):
    """rows: dicts with any of STAT_COLS; the rest default to 0/REG/2026."""
    base = dict(season=2026, season_type="REG", attempts=0, carries=0, targets=0, passing_yards=0,
                rushing_yards=0, receiving_yards=0, opponent_team="ZZZ")
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["player_display_name"] = out.get("player_display_name", out.player_id)
    return out[STAT_COLS]
