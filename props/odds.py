"""Sportsbook prop lines for the Top plays board (The Odds API, key from the ODDS_API_KEY environment variable).

One puller for the whole project. The refresh build pulls only when it matters:
  auto   games kicking off within ODDS_WINDOW_HOURS that were not pulled in the last ODDS_REPULL_HOURS
         (the Sunday 7am ET run gets Sunday's games, the Thursday / Monday morning runs get TNF / MNF)
  force  every game left in the first slate week (the manual "pull lines now" run)
  off    nothing
Every US book's lines are saved to history/odds/<season>/<UTC pull time>.json (the archive step commits them), so later
builds reuse the latest pull for games that have not started, and the lines stay available for research.  Picks use
ODDS_BOOK (DraftKings) only.  Listing events is free; each game's odds call costs (markets x regions) credits.  With no key
nothing is pulled and nothing breaks: the board falls back to target numbers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import requests

from . import config as C
from .linelog import API, MARKETS, norm_name

VERSION = 1
TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
    "Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC", "Las Vegas Raiders": "LV", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "Seattle Seahawks": "SEA",
    "San Francisco 49ers": "SF", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?")


def _utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _iso(ts) -> str:
    return _utc(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(name: str) -> str:
    """First initial + last name ("A. St. Brown" and "Amon-Ra St. Brown" both -> "abrown"... after suffixes are dropped)."""
    parts = [p for p in _SUFFIX.sub("", str(name).lower()).replace(".", " ").split() if p]
    return (parts[0][0] + re.sub(r"[^a-z]", "", parts[-1])) if len(parts) >= 2 else norm_name(name)


# ---- matching book names to nflverse players -----------------------------------------------------------------------
def roster_index(roster: pd.DataFrame) -> dict:
    """{"full": {team: {normalised name: pid}}, "short": {team: {initial+last: {pid, ...}}}} from each player's latest row."""
    idx = {"full": {}, "short": {}}
    if roster is None or roster.empty:
        return idx
    r = roster.sort_values("week").drop_duplicates("gsis_id", keep="last") if "week" in roster else roster.drop_duplicates("gsis_id")
    for team, name, pid in zip(r.team, r.full_name, r.gsis_id):
        if pd.isna(pid) or pd.isna(name) or pd.isna(team):
            continue
        idx["full"].setdefault(team, {})[norm_name(name)] = pid
        idx["short"].setdefault(team, {}).setdefault(_short(name), set()).add(pid)
    return idx


def match(idx: dict, player: str, teams) -> str | None:
    """The player's id among the game's two teams: exact normalised name first, then a unique initial + last name."""
    n = norm_name(player)
    for t in teams:
        pid = idx["full"].get(t, {}).get(n)
        if pid:
            return pid
    hits = set()
    for t in teams:
        hits |= idx["short"].get(t, {}).get(_short(player), set())
    return next(iter(hits)) if len(hits) == 1 else None


# ---- pulling ---------------------------------------------------------------------------------------------------------
def _files(out_dir, season: int) -> list[Path]:
    d = Path(out_dir) / str(season)
    return sorted(d.glob("*.json")) if d.exists() else []


def recently_pulled(out_dir, season: int, now) -> set:
    """Event ids pulled within the last ODDS_REPULL_HOURS."""
    cutoff, ids = _utc(now) - pd.Timedelta(hours=C.ODDS_REPULL_HOURS), set()
    for p in _files(out_dir, season):
        doc = json.loads(p.read_text())
        if _utc(doc["pulled"]) >= cutoff:
            ids |= {e["id"] for e in doc.get("events", [])}
    return ids


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def pull(key: str | None, season: int, now, mode: str, out_dir, roster: pd.DataFrame, last_kickoff=None,
         get=requests.get) -> tuple[Path | None, str]:
    """Pull the chosen games' prop lines and save them.  Returns (file written or None, a one-line note for the page/log)."""
    if mode == "off":
        return None, ""
    if not key:
        return None, "No ODDS_API_KEY set, so no sportsbook lines were pulled."
    now_u = _utc(now)
    try:
        r = get(f"{API}/events", params={"apiKey": key}, timeout=30)
        r.raise_for_status()
        events = r.json()
    except (requests.RequestException, ValueError) as e:
        return None, f"Could not list games from The Odds API ({type(e).__name__})."
    recent = recently_pulled(out_dir, season, now_u)
    last = _utc(last_kickoff) if last_kickoff is not None else None
    chosen = []
    for e in events:
        k = _utc(e["commence_time"])
        if k <= now_u:
            continue
        if mode == "force":
            if last is None or k <= last:
                chosen.append(e)
        elif k <= now_u + pd.Timedelta(hours=C.ODDS_WINDOW_HOURS) and e["id"] not in recent:
            chosen.append(e)
    if not chosen:
        return None, "No games inside the line-pull window right now."

    idx, lines, pulled, remaining, used, failed = roster_index(roster), [], [], None, None, 0
    for e in chosen:
        if remaining is not None and remaining < C.ODDS_MIN_REMAINING:
            break
        try:
            r = get(f"{API}/events/{e['id']}/odds", timeout=30,
                    params={"apiKey": key, "regions": "us", "markets": ",".join(MARKETS), "oddsFormat": "american"})
            r.raise_for_status()
            body = r.json()
        except (requests.RequestException, ValueError):
            failed += 1
            continue
        hdr = getattr(r, "headers", {}) or {}
        remaining = _int(hdr.get("x-requests-remaining", remaining))
        used = _int(hdr.get("x-requests-used", used))
        teams = [TEAM_ABBR.get(e.get("home_team")), TEAM_ABBR.get(e.get("away_team"))]
        pulled.append(dict(id=e["id"], kickoff=_iso(e["commence_time"]), home=teams[0], away=teams[1]))
        for bk in body.get("bookmakers", []):
            for mk in bk.get("markets", []):
                m = MARKETS.get(mk.get("key"))
                if not m:
                    continue
                for o in mk.get("outcomes", []):
                    player = o.get("description") or o.get("name")
                    lines.append(dict(event=e["id"], kickoff=_iso(e["commence_time"]), book=bk.get("key"),
                                      updated=mk.get("last_update"), market=m, player=player,
                                      pid=match(idx, player, [t for t in teams if t]), side=o.get("name"),
                                      point=o.get("point"), price=o.get("price")))
    if not pulled:
        return None, f"The Odds API did not return lines for {failed} game(s)."
    doc = dict(version=VERSION, pulled=_iso(now_u), mode=mode, regions="us", markets=list(MARKETS),
               remaining=remaining, used=used, events=pulled, lines=lines)
    path = Path(out_dir) / str(season) / (doc["pulled"].replace(":", "-") + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    stop = " Stopped early: few credits left." if remaining is not None and remaining < C.ODDS_MIN_REMAINING else ""
    return path, (f"Pulled lines for {len(pulled)} game(s), {len(lines)} prices; {remaining if remaining is not None else '?'}"
                  f" credits left.{stop}")


# ---- loading ---------------------------------------------------------------------------------------------------------
def load(out_dir, season: int, now, days: int = 10) -> tuple[pd.DataFrame, dict]:
    """Latest saved price per (game, book, market, player, side) for games that have not started, plus pull info."""
    now_u, rows, docs = _utc(now), [], []
    for p in _files(out_dir, season):
        doc = json.loads(p.read_text())
        if _utc(doc["pulled"]) < now_u - pd.Timedelta(days=days):
            continue
        docs.append(doc)
        teams = {e["id"]: (e.get("home"), e.get("away")) for e in doc.get("events", [])}
        rows += [{**ln, "pulled": doc["pulled"], "home": teams.get(ln["event"], (None, None))[0],
                  "away": teams.get(ln["event"], (None, None))[1]} for ln in doc.get("lines", [])]
    meta = {"pulled": None, "remaining": docs[-1].get("remaining") if docs else None, "book_lines": 0, "unmatched": 0}
    if not rows:
        return pd.DataFrame(), meta
    df = pd.DataFrame(rows)
    df = df[pd.to_datetime(df.kickoff, utc=True) > now_u]
    df = df.sort_values("pulled").drop_duplicates(["event", "book", "market", "player", "side"], keep="last")
    book = df[df.book == C.ODDS_BOOK]
    meta.update(pulled=book.pulled.max() if len(book) else (df.pulled.max() if len(df) else None),
                book_lines=int(len(book)), unmatched=int(book.pid.isna().sum()) if len(book) else 0)
    return df.reset_index(drop=True), meta


def book_lines(df: pd.DataFrame, book: str = C.ODDS_BOOK) -> dict:
    """{(pid, market): [line, ...]} for one book.  Yardage: point + Over/Under prices; anytime TD: the Yes price.

    A player has one line per game, but the list allows two games (two slate weeks) to coexist; picks match on kickoff.
    """
    out = {}
    if df is None or df.empty:
        return out
    b = df[(df.book == book) & df.pid.notna()]
    for (pid, market, event), g in b.groupby(["pid", "market", "event"]):
        kick, upd = g.kickoff.iloc[0], g.updated.max()
        teams = [t for t in (g.home.iloc[0] if "home" in g else None, g.away.iloc[0] if "away" in g else None) if t]
        if market == "TD":
            yes = g[g.side == "Yes"]
            if len(yes):
                out.setdefault((pid, market), []).append(dict(kickoff=kick, updated=upd, teams=teams, yes=int(yes.price.iloc[0])))
            continue
        best = None
        for point, h in g.groupby("point"):                    # normally one point; if not, take the most even pair
            o, u = h[h.side == "Over"], h[h.side == "Under"]
            if not len(o) and not len(u):
                continue
            ln = dict(kickoff=kick, updated=upd, teams=teams, point=float(point),
                      over=int(o.price.iloc[0]) if len(o) else None, under=int(u.price.iloc[0]) if len(u) else None)
            gap = abs((ln["over"] or 0) - (ln["under"] or 0))
            if best is None or gap < best[0]:
                best = (gap, ln)
        if best:
            out.setdefault((pid, market), []).append(best[1])
    return out


def line_for(lines: dict, pid, market: str, kickoff) -> dict | None:
    """The book's line for this player-market in the game that kicks off at `kickoff` (within 6 hours)."""
    if kickoff is None or pd.isna(kickoff):
        return None
    k = _utc(kickoff)
    for ln in lines.get((pid, market), []):
        if abs(_utc(ln["kickoff"]) - k) <= pd.Timedelta(hours=6):
            return ln
    return None
