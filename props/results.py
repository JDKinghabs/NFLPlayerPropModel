"""Actual results, published separately from the pre-game page data.

The website grades logged bets against this file.  It never feeds back into a bet's frozen snapshot.
Keys:  final -> "season|week|team" for every team whose game that week is in the data;
       y     -> "season|week|player_id|CAT" = actual yards for the prop category (QB pass / RB rush / WR rec);
       t     -> same keys = actual touches (QB attempts, RB carries + catches, WR targets).
A final team with no entry for a player means he recorded no stat line (graded as void / DNP).
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from .volume import touch_col


def build_results(stats: pd.DataFrame, season: int) -> dict:
    if stats is None or stats.empty:
        return {"season": season, "final": [], "y": {}, "t": {}}
    s = stats[stats.season == season]
    final = sorted({f"{season}|{int(w)}|{t}" for w, t in zip(s.week, s.team)})
    y, t = {}, {}
    for k, cat in C.CATS.items():
        d = s[s.position.isin(cat.positions)]
        for pid, w, v, tv in zip(d.player_id, d.week, d[cat.yards].fillna(0), touch_col(d, k)):
            key = f"{season}|{int(w)}|{pid}|{k}"
            y[key], t[key] = int(round(v)), int(round(tv))
    return {"season": season, "final": final, "y": y, "t": t}
