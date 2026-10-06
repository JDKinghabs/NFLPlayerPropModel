"""Sportsbook line log: at each refresh, record the books' prop lines next to the model's projections.

Writes `<dir>/<season>/<build time>.json`. Each file is self-contained so edge vs the market can be scored later
without re-running anything: `projections` is what the model said at that moment, `lines` is what the books posted.
Source: The Odds API (https://the-odds-api.com), key from the ODDS_API_KEY environment variable. With no key the log
is skipped, never an error. Listing events is free; each event's odds call costs (markets x regions) credits.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import requests

from . import config as C

API = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
MARKETS = {                       # Odds API market -> (our category, "yards" or "td")
    "player_pass_yds": "QB",
    "player_rush_yds": "RB",
    "player_reception_yds": "WR",
    "player_anytime_td": "TD",
}
LOG_VERSION = 1


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def projection_rows(res) -> list[dict]:
    """Flatten the model's projections (elite, backup and anytime-TD tabs) to one row per player/week/market."""
    out = []
    for sheet, tables in (("elite", res.elite), ("backup", res.backups)):
        for cat, df in tables.items():
            for r in df.itertuples():
                out.append(dict(market=cat, sheet=sheet, pid=r.player_id, name=r.name, team=r.team, week=int(r.week),
                                proj=round(float(r.proj), 2)))
    for grp, df in res.td.items():
        for r in df.itertuples():
            out.append(dict(market="TD", sheet="td", pid=r.player_id, name=r.name, team=r.team, week=int(r.week),
                            proj=round(float(r.p_td), 4)))
    return out


def fetch_lines(api_key: str, kickoffs_before=None, markets=tuple(MARKETS), regions="us", session=None) -> list[dict]:
    """One flat row per (book, market, player, side). Events kicking off after `kickoffs_before` are skipped."""
    s = session or requests
    p = {"apiKey": api_key}
    events = s.get(f"{API}/events", params=p, timeout=30)
    events.raise_for_status()
    rows = []
    for ev in events.json():
        if kickoffs_before is not None and ev["commence_time"] > kickoffs_before:
            continue
        r = s.get(f"{API}/events/{ev['id']}/odds", timeout=30,
                  params={**p, "regions": regions, "markets": ",".join(markets), "oddsFormat": "american"})
        r.raise_for_status()
        for bk in r.json().get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] not in MARKETS:
                    continue
                for o in mk.get("outcomes", []):
                    rows.append(dict(event=ev["id"], home=ev["home_team"], away=ev["away_team"],
                                     kickoff=ev["commence_time"], book=bk["key"], book_updated=mk.get("last_update"),
                                     market=MARKETS[mk["key"]], player=o.get("description") or o.get("name"),
                                     side=o["name"], point=o.get("point"), price=o["price"]))
    return rows


def attach_projections(lines: list[dict], projections: list[dict]) -> list[dict]:
    """Tag each line with the model's pid/projection when the same player-market is in the projections."""
    idx = {(p["market"], norm_name(p["name"])): p for p in projections}
    for ln in lines:
        p = idx.get((ln["market"], norm_name(ln["player"])))
        ln["pid"] = p["pid"] if p else None
        ln["proj"] = p["proj"] if p else None
    return lines


def write_log(res, out_dir, lines: list[dict]) -> Path:
    gen = res.meta["generated"]
    projections = projection_rows(res)
    doc = dict(log_version=LOG_VERSION, season=res.season, built=gen.isoformat(), weeks=res.meta["weeks"],
               model=C.MODEL_VERSION, projections=projections, lines=attach_projections(lines, projections))
    path = Path(out_dir) / str(res.season) / f"{gen.strftime('%Y-%m-%dT%H-%M-%S%z')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")))
    return path


def log_lines(res, out_dir, api_key: str | None = None, session=None) -> Path | None:
    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        print("Line log skipped: set ODDS_API_KEY to record sportsbook lines.")
        return None
    last = res.slate.kickoff.max()
    lines = fetch_lines(key, kickoffs_before=last.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), session=session)
    return write_log(res, out_dir, lines)
