"""Frozen archive of every pre-game prediction the site shows.

`python -m props --history history` saves one JSON snapshot per refresh, history/<season>/<UTC build time>.json, holding every
anytime-TD probability, yardage projection (every top-N player and Sheet 2) and QB flag as the model had them at that moment,
plus the Top plays board's picks with the price they were graded against.  Why:
the website is rebuilt from scratch each time, so without this nothing remembers what the model said before a game, and
nothing can be graded against what happened.

A snapshot can never contain hindsight.  The slate only holds games that had not kicked off at build time, and as a second
safeguard any row whose kickoff is not strictly after the build time (or has no kickoff) is dropped.  So the LATEST snapshot a
game appears in is the last thing the model said before kickoff, which is what a scorecard should grade.  A snapshot identical
to the previous one (same predictions, ignoring the build time) is not written again.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from . import config as C
from .td import TD_GROUPS

VERSION = 1

# (key in the file, column in the frame, kind): s str | i int | b bool | t timestamp (UTC ISO) | f1..f4 float rounded to that many places
TD_FIELDS = [("week", "week", "i"), ("pid", "player_id", "s"), ("name", "name", "s"), ("team", "team", "s"), ("opp", "opp", "s"),
             ("pos", "grp", "s"), ("kickoff", "kickoff", "t"), ("p_td", "p_td", "f4"), ("tt", "tt", "f2"), ("xtd", "xtd", "f3"),
             ("touch", "pg_touch", "f2"), ("games", "n_prev", "i"), ("inj", "inj", "s"), ("p_out", "p_out", "f3"),
             ("role_up", "role_up", "b")]
ELITE_FIELDS = [("week", "week", "i"), ("pid", "player_id", "s"), ("name", "name", "s"), ("team", "team", "s"), ("opp", "opp", "s"),
                ("kickoff", "kickoff", "t"), ("proj", "proj", "f2"), ("opp_rank", "opp_rank", "i"), ("rank", "rank", "i"),
                ("exp_touches", "t_exp", "f2"), ("inj", "inj", "s"), ("p_out", "p_out", "f3"), ("qb_flag", "q_flag", "b"),
                ("qb_p", "q_p", "f3"), ("qb_if", "q_if", "f1")]
BACKUP_FIELDS = [("week", "week", "i"), ("pid", "player_id", "s"), ("name", "name", "s"), ("team", "team", "s"), ("opp", "opp", "s"),
                 ("kickoff", "kickoff", "t"), ("proj_exp", "proj_exp", "f2"), ("proj_if_out", "proj_if_out", "f2"),
                 ("p_out", "p_out", "f3"), ("starters_out", "starters_out", "s"), ("role", "role", "s"), ("inj", "inj", "s")]


def _iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _conv(v, kind: str):
    """A plain, JSON-safe value (numpy scalars, NaN and NaT -> None)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if kind == "s":
        return str(v)
    if kind == "i":
        return int(v)
    if kind == "b":
        return bool(v)
    if kind == "t":
        return _iso(v)
    return round(float(v), int(kind[1:]))


def _rows(df, fields, built: str, cat: str | None = None) -> list:
    if df is None or len(df) == 0:
        return []
    out = []
    for rec in df.to_dict("records"):
        r = {k: _conv(rec.get(col), kind) for k, col, kind in fields}
        if cat:
            r = {"cat": cat, **r}
        if r["kickoff"] and r["kickoff"] > built:            # the freeze: nothing at or after kickoff, nothing undated
            out.append(r)
    return out


def snapshot(res) -> dict:
    """Everything the model said before kickoff, as plain data.  `hash` covers the predictions only (not the build time)."""
    m = res.meta
    built = _iso(m["generated"])
    td = [r for g in TD_GROUPS for r in _rows((getattr(res, "td", None) or {}).get(g), TD_FIELDS, built)]
    elite = [r for k in C.CATS for r in _rows((getattr(res, "elite_all", None) or res.elite).get(k), ELITE_FIELDS, built, k)]
    picks = [{k: v for k, v in p.items() if k not in ("game",)} for p in getattr(res, "picks", None) or []
             if p.get("kickoff") and p["kickoff"] > built]
    backup = [r for k in C.CATS for r in _rows(res.backups.get(k), BACKUP_FIELDS, built, k)]
    body = {"version": VERSION, "season": int(res.season), "weeks": [int(w) for w in m.get("weeks", [])],
            "model": {"yardage": m.get("model", C.MODEL_VERSION), "td": m.get("td_model", "")},
            "td": td, "elite": elite, "backup": backup, "picks": picks}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return {**body, "built": built, "hash": digest, "code_sha": os.environ.get("GITHUB_SHA", "")}


def _last_hash(path: Path):
    try:
        return json.loads(path.read_text()).get("hash")
    except (OSError, ValueError):
        return None


def write_snapshot(res, root) -> Path | None:
    """Write history/<season>/<build time>.json unless nothing is left before kickoff or it matches the previous snapshot."""
    snap = snapshot(res)
    if not (snap["td"] or snap["elite"] or snap["backup"]):
        return None
    d = Path(root) / str(snap["season"])
    existing = sorted(d.glob("*.json")) if d.exists() else []
    if existing and _last_hash(existing[-1]) == snap["hash"]:
        return None
    d.mkdir(parents=True, exist_ok=True)
    path = d / (snap["built"].replace(":", "-") + ".json")          # sorts by time; no colons, so it is a legal name everywhere
    path.write_text(json.dumps(snap, separators=(",", ":")) + "\n")
    return path
