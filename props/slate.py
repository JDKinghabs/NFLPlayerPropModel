"""Pick the games to analyse and reshape them to one row per team."""
from __future__ import annotations

import pandas as pd

ET = "America/New_York"


def _kickoff(games: pd.DataFrame) -> pd.Series:
    t = games.gametime.fillna("13:00")
    return pd.to_datetime(games.gameday + " " + t).dt.tz_localize(ET, nonexistent="shift_forward",
                                                                   ambiguous="NaT")


def select_slate(games: pd.DataFrame, season: int, weeks: list[int] | None = None,
                 now: pd.Timestamp | None = None, include_started: bool = False) -> pd.DataFrame:
    """One row per (game, team) for games that have not kicked off.

    weeks=None -> the earliest week that still has a game to play.
    """
    now = now if now is not None else pd.Timestamp.now(tz=ET)
    g = games[(games.season == season) & (games.game_type == "REG")].copy()
    g["kickoff"] = _kickoff(g)
    open_game = g.home_score.isna() & (include_started | (g.kickoff > now))
    if weeks is None:
        pending = g[open_game]
        if pending.empty:
            return _team_rows(pending)
        weeks = [int(pending.week.min())]
    g = g[open_game & g.week.isin(weeks)]
    return _team_rows(g)


def _team_rows(g: pd.DataFrame) -> pd.DataFrame:
    cols = ["game_id", "week", "kickoff", "team", "opp", "home", "spread", "ou"]
    if g.empty:
        return pd.DataFrame(columns=cols)
    # nflverse spread_line > 0 means the HOME team is favoured; convert to book notation
    # (negative = favourite) from each team's point of view.
    home = pd.DataFrame({"game_id": g.game_id, "week": g.week, "kickoff": g.kickoff,
                         "team": g.home_team, "opp": g.away_team, "home": True,
                         "spread": -g.spread_line, "ou": g.total_line})
    away = pd.DataFrame({"game_id": g.game_id, "week": g.week, "kickoff": g.kickoff,
                         "team": g.away_team, "opp": g.home_team, "home": False,
                         "spread": g.spread_line, "ou": g.total_line})
    return pd.concat([home, away], ignore_index=True)[cols].sort_values(["kickoff", "game_id"])


def fmt_opp(row) -> str:
    return ("" if row["home"] else "@") + str(row["opp"])


def fmt_kick(ts: pd.Timestamp) -> str:
    if pd.isna(ts):
        return ""
    h = ts.hour % 12 or 12
    suffix = "a" if ts.hour < 12 else "p"
    mins = f":{ts.minute:02d}" if ts.minute else ""
    return f"{ts.strftime('%a')} {ts.month}/{ts.day} {h}{mins}{suffix}"


def fmt_spread_total(spread, total) -> str:
    if pd.isna(spread) or pd.isna(total):
        return ""
    s = "PK" if spread == 0 else f"{spread:+.1f}".replace(".0", "")
    return f"{s} / {total:g}"
