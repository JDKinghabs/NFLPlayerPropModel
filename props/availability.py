"""Who is (probably) not playing: injury report + roster status -> P(out)."""
from __future__ import annotations

import pandas as pd

from . import config as C


def injury_week_for(injuries: pd.DataFrame, week: int) -> tuple[pd.DataFrame, bool, int | None]:
    """Injury rows to use for a slate week.

    Returns (rows, stale, report_week). If no report exists yet for `week` we fall back to the
    previous week's report and flag it stale.  Anything older is ignored: the carry-over odds were
    calibrated for exactly one week, and a two-week-old "Out" says little.
    """
    if injuries is None or injuries.empty:
        return pd.DataFrame(), False, None
    inj = injuries[injuries.game_type.fillna("REG") == "REG"] if "game_type" in injuries else injuries
    avail = sorted(inj.week.unique())
    if week in avail:
        return inj[inj.week == week], False, week
    earlier = [w for w in avail if w < week]
    if earlier and week - earlier[-1] == 1:          # carry-over odds are only calibrated for 1 week
        return inj[inj.week == earlier[-1]], True, int(earlier[-1])
    return pd.DataFrame(), False, None


def _played_in_week(stats: pd.DataFrame | None, week: int | None) -> tuple[set, set]:
    """(players with volume that week, teams whose game that week is already in the data)."""
    if stats is None or stats.empty or week is None:
        return set(), set()
    s = stats[stats.week == week]
    vol = s[["attempts", "carries", "targets"]].fillna(0).sum(axis=1)
    return set(s.player_id[vol > 0]), set(s.team)


def p_out_table(injuries: pd.DataFrame, roster: pd.DataFrame, week: int,
                stats: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per player with some chance of missing the game.

    `stats` (current-season player-weeks) lets a stale report distinguish a Questionable
    player who sat last week from one who played.
    Columns: gsis_id, p_out, label, stale, source  (source: 'injury' report or 'roster' status such as IR)
    """
    rows = []
    rows_inj, stale, rep_wk = injury_week_for(injuries, week)
    played, teams_done = _played_in_week(stats, rep_wk) if stale else (set(), set())
    for r in rows_inj.itertuples():
        status = (r.report_status or "") if isinstance(r.report_status, str) else ""
        practice = r.practice_status if isinstance(r.practice_status, str) else ""
        pos = getattr(r, "position", "")
        p, label = 0.0, ""
        if stale:
            tag = f"wk{rep_wk} rpt"
            if status == "Out":
                p, label = C.P_OUT_STALE_OUT, f"OUT ({tag})"
            elif status == "Doubtful":
                p, label = C.P_OUT_STALE_DOUBTFUL, f"DOUBT ({tag})"
            elif status == "Questionable" and r.team in teams_done and r.gsis_id not in played:
                p, label = C.P_OUT_STALE_Q_DNP, f"Q, sat ({tag})"
        elif status == "Out":
            p, label = 1.0, "OUT"
        elif status == "Doubtful":
            p, label = 1.0, "DOUBTFUL"
        elif status == "Questionable":
            p = C.P_OUT_QUESTIONABLE_QB if pos == "QB" else C.P_OUT_QUESTIONABLE
            label = f"Q ({p:.0%})"
        elif not status and practice.startswith("Did Not"):
            p, label = C.P_OUT_PRACTICE_DNP, f"DNP ({C.P_OUT_PRACTICE_DNP:.0%})"
        if p > 0:
            rows.append((r.gsis_id, p, label, stale))
    inj_df = pd.DataFrame(rows, columns=["gsis_id", "p_out", "label", "stale"]).assign(source="injury")

    # roster-level unavailability (IR / suspended / retired / cut) is certain
    ro = roster[roster.status.isin(C.ROSTER_UNAVAILABLE)]
    ro = ro.assign(p_out=1.0, label=ro.status.map(lambda s: "IR/RES" if s == "RES" else s),
                   stale=False, source="roster")[["gsis_id", "p_out", "label", "stale", "source"]]
    out = pd.concat([inj_df, ro], ignore_index=True)
    out = out[out.gsis_id.notna()].sort_values("p_out", ascending=False)
    return out.drop_duplicates("gsis_id").reset_index(drop=True)
