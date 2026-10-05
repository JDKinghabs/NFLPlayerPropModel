"""Offensive snap share (nflverse snap counts) as a role signal for who absorbs a missing starter's volume."""
from __future__ import annotations

import pandas as pd


def prepare_snaps(snap_df: pd.DataFrame, id_map: pd.DataFrame) -> pd.DataFrame:
    """Regular-season rows with a gsis_id: gsis_id, team, week, offense_snaps, offense_pct.

    `id_map` needs pfr_id and gsis_id (any roster file has both).
    """
    cols = ["gsis_id", "team", "week", "offense_snaps", "offense_pct"]
    if snap_df is None or snap_df.empty or id_map is None or id_map.empty:
        return pd.DataFrame(columns=cols)
    s = snap_df[snap_df.game_type == "REG"] if "game_type" in snap_df else snap_df
    m = id_map.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id")[["pfr_id", "gsis_id"]]
    s = s.merge(m, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    s = s[s.offense_snaps > 0]
    return s[cols].reset_index(drop=True)


def recent_share(snaps: pd.DataFrame, team: str, n: int = 3) -> dict:
    """gsis_id -> mean offensive snap share over the player's last `n` games with this team."""
    if snaps is None or snaps.empty:
        return {}
    t = snaps[snaps.team == team].sort_values("week")
    return t.groupby("gsis_id").offense_pct.apply(lambda x: float(x.tail(n).mean())).to_dict()
