"""Game-script adjustment from the betting market's view of the game (spread and total).

Only QB passing yards use it: in leave-one-season-out tests on 2022-25 the implied team total (t = 3.2) and
home field (t = 2.6) helped QBs, while RB and WR showed no reliable out-of-sample gain
(research/experiment_game_context.py).
"""
from __future__ import annotations

import pandas as pd

from . import config as C


def context_effect(cat_key: str, spread, ou, home) -> float:
    """Percent change to the projection from this game's expected scoring and home field (0 if not modelled)."""
    c = C.GAME_SCRIPT.get(cat_key)
    if not c:
        return 0.0
    if pd.isna(spread) or pd.isna(ou):
        tt_gap = c["tt_ref"]                               # no line posted yet: assume a typical elite-QB game
    else:
        team_total = ou / 2 + (-spread) / 2                # spread < 0 means this team is favoured
        tt_gap = team_total / C.LEAGUE_TEAM_TOTAL - 1
    return c["tt"] * (tt_gap - c["tt_ref"]) + c["home"] * ((1.0 if bool(home) else 0.0) - 0.5)


def multiplier(cat_key: str, spread, ou, home, level: bool = True) -> float:
    """1 + level correction + context effect.  `level` is only validated for the Sheet 1 elite pool."""
    c = C.GAME_SCRIPT.get(cat_key)
    if not c:
        return 1.0
    return 1.0 + (c["level"] if level else 0.0) + context_effect(cat_key, spread, ou, home)
