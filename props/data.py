"""Download + cache nflverse data (https://github.com/nflverse/nflverse-data)."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from .snaps import prepare_snaps

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

STAT_COLS = [
    "player_id", "player_display_name", "position", "team", "opponent_team", "season", "week",
    "season_type", "attempts", "carries", "targets", "receptions", "passing_yards", "rushing_yards",
    "receiving_yards",
]


def _fetch(url: str, dest: Path, retries: int = 4) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    delay = 2.0
    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                tmp.replace(dest)
                return
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2


def cached(path: str, live: bool, max_age_hours: float = 3.0, refresh: bool = False,
           required: bool = True) -> Path | None:
    """Return a local copy of an nflverse release file, downloading when stale.

    `live` files change during the season and are re-fetched after `max_age_hours`;
    finished-season files are fetched once.
    """
    dest = CACHE_DIR / Path(path).name
    stale = refresh or not dest.exists() or (
        live and time.time() - dest.stat().st_mtime > max_age_hours * 3600)
    if stale:
        try:
            _fetch(f"{BASE}/{path}", dest)
        except requests.RequestException:
            if dest.exists():          # fall back to an older copy rather than fail
                return dest
            if required:
                raise
            return None
    return dest


def current_season(today: pd.Timestamp | None = None) -> int:
    today = today or pd.Timestamp.now(tz="America/New_York")
    return today.year if today.month >= 3 else today.year - 1


def load_all(season: int, refresh: bool = False, max_age_hours: float = 3.0) -> dict:
    """Everything the model needs, as a dict of DataFrames."""
    kw = dict(refresh=refresh, max_age_hours=max_age_hours)
    games = pd.read_csv(cached("schedules/games.csv", True, **kw))

    def stats(year: int, live: bool) -> pd.DataFrame:
        p = cached(f"stats_player/stats_player_week_{year}.csv", live, required=live, **kw)
        if p is None:
            return pd.DataFrame(columns=STAT_COLS)
        d = pd.read_csv(p, usecols=lambda c: c in STAT_COLS)
        return d[d.season_type == "REG"].copy()

    inj_p = cached(f"injuries/injuries_{season}.csv", True, required=False, **kw)
    injuries = pd.read_csv(inj_p) if inj_p else pd.DataFrame()
    roster = pd.read_csv(cached(f"rosters/roster_{season}.csv", True, **kw),
                         usecols=["team", "position", "full_name", "gsis_id", "pfr_id", "status", "week"])
    dc_p = cached(f"depth_charts/depth_charts_{season}.csv", True, required=False, **kw)
    depth = _latest_depth(dc_p)
    sn_p = cached(f"snap_counts/snap_counts_{season}.csv", True, required=False, **kw)
    snaps = prepare_snaps(pd.read_csv(sn_p), roster) if sn_p else prepare_snaps(None, None)
    return {
        "snaps": snaps,
        "games": games,
        "stats": stats(season, True),
        "prev_stats": stats(season - 1, False),
        "injuries": injuries,
        "roster": roster,
        "depth": depth,
    }


def _latest_depth(path: Path | None) -> pd.DataFrame:
    """Latest depth-chart snapshot per team, offensive skill positions only."""
    cols = ["dt", "team", "player_name", "gsis_id", "pos_abb", "pos_rank"]
    if path is None:
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, usecols=cols)
    d = d[d.pos_abb.isin(["QB", "RB", "FB", "WR", "TE"]) & d.gsis_id.notna()]
    last = d.groupby("team").dt.transform("max")
    return d[d.dt == last].drop(columns="dt").reset_index(drop=True)
