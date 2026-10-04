"""Glue: load data -> pick slate -> build both sheets' tables."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config as C
from .availability import injury_week_for, p_out_table
from .backups import backup_table
from .data import current_season, load_all
from .defense import defense_ratings
from .elite import elite_table
from .slate import ET, select_slate


@dataclass
class Result:
    season: int
    slate: pd.DataFrame
    ratings: dict
    elite: dict
    backups: dict
    meta: dict = field(default_factory=dict)


def build(season: int | None = None, weeks: list[int] | None = None, refresh: bool = False,
          include_started: bool = False, now: pd.Timestamp | None = None,
          top_n: int = C.ELITE_TOP_N, weak_n: int = C.WEAK_DEF_N, data: dict | None = None) -> Result:
    now = now if now is not None else pd.Timestamp.now(tz=ET)
    season = season or current_season(now)
    d = data or load_all(season, refresh=refresh)
    if d["stats"].empty:
        raise SystemExit(f"No {season} regular-season games have been played yet - nothing to model.")
    slate = select_slate(d["games"], season, weeks, now=now, include_started=include_started)

    ratings = {k: defense_ratings(d["stats"], d["prev_stats"], cat) for k, cat in C.CATS.items()}
    slate_weeks = sorted(slate.week.unique()) if len(slate) else []
    pout = {w: p_out_table(d["injuries"], d["roster"], int(w), d["stats"]) for w in slate_weeks}

    elite, backups = {}, {}
    for k, cat in C.CATS.items():
        if slate.empty:
            elite[k], backups[k] = pd.DataFrame(), pd.DataFrame()
            continue
        elite[k] = elite_table(cat, d["stats"], d["prev_stats"], ratings[k], slate, pout,
                               top_n=top_n, weak_n=weak_n)
        backups[k] = backup_table(cat, d["stats"], d["prev_stats"], ratings[k], slate, d["depth"],
                                  d["roster"], pout, injuries_names=d["injuries"])

    inj_notes = {}
    for w in slate_weeks:
        _, stale, rep = injury_week_for(d["injuries"], int(w))
        inj_notes[int(w)] = (rep, stale)
    meta = {
        "generated": now,
        "weeks": [int(w) for w in slate_weeks],
        "games": int(len(slate) // 2),
        "data_through_week": int(d["stats"].week.max()) if len(d["stats"]) else 0,
        "injury_reports": inj_notes,
        "top_n": top_n, "weak_n": weak_n,
    }
    return Result(season, slate, ratings, elite, backups, meta)
