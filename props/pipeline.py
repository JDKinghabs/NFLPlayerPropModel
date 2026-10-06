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
from .results import build_results
from .slate import ET, select_slate
from .td import TD_GROUPS, load_model, td_table


@dataclass
class Result:
    season: int
    slate: pd.DataFrame
    ratings: dict
    elite: dict
    backups: dict
    meta: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    td: dict = field(default_factory=dict)          # anytime-TD tab: {"RB"/"WR"/"TE": ranked DataFrame}


def build(season: int | None = None, weeks: list[int] | None = None, refresh: bool = False,
          include_started: bool = False, now: pd.Timestamp | None = None, lookahead: int = 1,
          top_n: int | None = None, weak_n: int = C.WEAK_DEF_N, data: dict | None = None) -> Result:
    now = now if now is not None else pd.Timestamp.now(tz=ET)
    season = season or current_season(now)
    d = data or load_all(season, refresh=refresh)
    if d["stats"].empty:
        raise SystemExit(f"No {season} regular-season games have been played yet - nothing to model.")
    slate = select_slate(d["games"], season, weeks, now=now, include_started=include_started,
                         lookahead=lookahead)

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
                                  d["roster"], pout, injuries_names=d["injuries"], snaps=d.get("snaps"))

    td, td_note, model = {k: pd.DataFrame() for k in TD_GROUPS}, "", load_model()
    if not slate.empty and model is not None:
        # a starter who is out means his backup's role is bigger than his season average says (see the Backups tab)
        bk = {k: set(b.player_id[b.p_out >= 0.5]) for k, b in backups.items() if b is not None and len(b)}
        try:
            td = td_table(d["stats"], d["prev_stats"], d.get("pbp"), d.get("prev_pbp"), d["roster"], slate, pout, model,
                          backup_ids=bk.get("RB", set()) | bk.get("WR", set()))
        except Exception as e:                       # an optional tab must never take the whole site down
            td_note = f"The anytime-TD tab could not be built this time ({type(e).__name__})."
    if model is not None and not any(len(v) for v in td.values()) and not td_note:
        td_note = "No anytime-TD rows for this slate yet (play-by-play data not available)."

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
        "top_n": {k: (top_n or cat.elite_n) for k, cat in C.CATS.items()}, "weak_n": weak_n, "model": C.MODEL_VERSION,
        "td_note": td_note, "td_model": (model or {}).get("version", ""),
    }
    return Result(season, slate, ratings, elite, backups, meta, build_results(d["stats"], season), td)
