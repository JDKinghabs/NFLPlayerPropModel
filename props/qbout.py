"""QB-out flag for Sheet 1 receivers: their starting QB may miss the game for the first time.

Validated in research/experiment_qb_out.py (walk-forward 2022-25, t-stats clustered by team-game): in a QB's FIRST missed
game top-25 WRs fell about 22% in receiving yards and 12% in targets vs their baseline (t = -2.6, 60 team-games, negative in
every season).  A longer absence shows nothing, because the season averages already contain it.  The effect is large but rare
(about 25 team-games a season), so it is shown as a FLAG with the historical size, like the RB/WR workload flag, and is not
folded into the projection.
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from .config import Category

COLS = ["q_flag", "q_txt", "q_p", "q_if"]


def starter_qb(stats: pd.DataFrame, team: str, week: int):
    """(player_id, name, games missed in a row) for the team's QB with the most attempts before `week`; None if no QB threw."""
    t = stats[(stats.team == team) & (stats.week < week)]
    q = t[(t.position == "QB") & (t.attempts.fillna(0) > 0)]
    if q.empty:
        return None
    pid = q.groupby("player_id").attempts.sum().idxmax()
    mine = q[q.player_id == pid]
    streak = 0
    for w in sorted(t.week.unique(), reverse=True):
        if mine[mine.week == w].attempts.sum() > 0:
            break
        streak += 1
    return pid, mine.player_display_name.iloc[-1], streak


def fresh_qb_risk(stats: pd.DataFrame, pout: pd.DataFrame | None, team: str, week: int):
    """(name, P(out), label) when the starting QB may miss this game and played the team's previous one, else None.

    A QB who has already missed games is not news: his absence is in the season averages the projections are built from.
    """
    s = starter_qb(stats, team, week)
    if s is None or pout is None or not len(pout):
        return None
    pid, name, streak = s
    if streak:
        return None
    hit = pout[pout.gsis_id == pid]
    if hit.empty or not hit.p_out.iloc[0] > 0:
        return None
    return name, float(hit.p_out.iloc[0]), str(hit.label.iloc[0])


def add_qb_flag(m: pd.DataFrame, cat: Category, stats: pd.DataFrame, pout_by_week: dict) -> pd.DataFrame:
    """Attach q_flag / q_txt / q_p / q_if to Sheet 1 rows (needs team, week, proj).  Only categories with a validated effect flag."""
    eff = C.QB_OUT_EFFECT.get(cat.key)
    cache, flag, txt, prob, if_out = {}, [], [], [], []
    for team, wk, proj in zip(m.team, m.week, m.proj):
        hit = None
        if eff is not None:
            if (team, wk) not in cache:
                cache[(team, wk)] = fresh_qb_risk(stats, pout_by_week.get(wk), team, int(wk))
            hit = cache[(team, wk)]
        flag.append(hit is not None)
        txt.append(f"{hit[0]} {hit[2]}" if hit else "")
        prob.append(hit[1] if hit else float("nan"))
        if_out.append(proj * (1 + eff["yards"]) if hit else float("nan"))
    return m.assign(q_flag=flag, q_txt=txt, q_p=prob, q_if=if_out)
