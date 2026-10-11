"""Tracked picks: a frozen card of the board's best picks, graded automatically once the games are final.

`python -m props.ledger log --snapshot history/<season>/<build>.json --top 10` copies the first N picks (board order: A before B,
then EV) from one archived pre-kickoff snapshot into history/ledger/<season>.json.  Logging is mechanical (rank order from a
snapshot built before kickoff), so nothing is picked with hindsight, and a logged entry is never edited: only its result fields
(`actual`, `outcome`, `units`) are filled in later.  Every build run with `--history` grades pending entries against the same
results the site uses (props/results.py), and the workflow's archive step commits the file.

Grading: yardage Over wins when actual > line, Under when actual < line, equal is a push; anytime TD wins on 1+ rushing or
receiving TDs.  A final team-week with no stat line for the player is void (most books void a non-starter).  1 unit per pick:
a win pays the American price, a loss costs 1, a push or void 0.

TD parlays (`log --parlays`) are logged the same way from the snapshot's parlays and kept as their own record: a parlay loses
as soon as one leg's game is final without a TD from him; a leg with no stat line drops out (books re-price the parlay without
it); it wins when every remaining leg scored, paying the product of their decimal prices; all legs void = void.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .picks import profit

FROZEN = ["rank", "grade", "kind", "market", "label", "pid", "name", "team", "opp_txt", "kick_txt", "kickoff", "week", "inj",
          "side", "line", "price", "p", "implied", "edge", "ev", "fair", "proj", "book", "updated", "reasons"]


def entry_id(season: int, e: dict) -> str:
    return f"{season}|{e['week']}|{e['pid']}|{e['market']}"


def card(snapshot: dict, n: int = 10, source: str = "") -> list:
    """The first n picks of an archived snapshot, frozen with where they came from."""
    season = snapshot["season"]
    out = []
    for p in sorted(snapshot.get("picks") or [], key=lambda p: p["rank"])[:n]:
        out.append({"id": entry_id(season, p), "season": season, **{k: p.get(k) for k in FROZEN},
                    "source": source, "source_built": snapshot.get("built"), "source_hash": snapshot.get("hash"),
                    "actual": None, "outcome": None, "units": None})
    return out


def card_parlays(snapshot: dict, source: str = "") -> list:
    """The snapshot's TD parlays, frozen like the picks (kind "parlay", one entry per parlay)."""
    season = snapshot["season"]
    out = []
    for x in snapshot.get("parlays") or []:
        legs = [{k: l.get(k) for k in ("pid", "name", "team", "pos", "opp_txt", "kick_txt", "kickoff", "week", "price", "p",
                                       "implied", "grade", "inj")} for l in x["legs"]]
        week = min(l["week"] for l in legs)
        out.append({"id": f"{season}|{week}|parlay|{x['type']}", "season": season, "week": week, "kind": "parlay",
                    "market": "PARLAY", "label": f"TD parlay · {x['type']}", "rank": x.get("rank"), "type": x["type"],
                    "name": " + ".join(l["name"] for l in legs), "team": "", "kickoff": min(l["kickoff"] for l in legs),
                    "kick_txt": legs[0]["kick_txt"], "side": "Yes", "line": None, "price": x["price"], "p": x["p"],
                    "implied": x["implied"], "edge": x["edge"], "ev": x["ev"], "grade": x.get("value_grade"),
                    "hit_grade": x.get("hit_grade"), "value_grade": x.get("value_grade"), "book": x.get("book"), "legs": legs,
                    "source": source, "source_built": snapshot.get("built"), "source_hash": snapshot.get("hash"),
                    "actual": None, "outcome": None, "units": None})
    return out


def load(path) -> list:
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def save(path, entries: list) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=1) + "\n")


def log(path, new: list, logged_at: str) -> list:
    """Append entries not already logged (by id); returns the ones added.  Existing entries are never touched."""
    entries = load(path)
    have = {e["id"] for e in entries}
    added = [{**e, "logged_at": logged_at} for e in new if e["id"] not in have]
    if added:
        save(path, entries + added)
    return added


def _settle_parlay(e: dict, results: dict):
    """(legs' TD counts, outcome, units) for a parlay, or None while it can still go either way."""
    final, td = set(results.get("final") or []), results.get("td") or {}
    status = []                                                   # per leg: "W" / "L" / "void" / None (pending)
    for l in e["legs"]:
        if f"{e['season']}|{l['week']}|{l['team']}" not in final:
            status.append(None)
            continue
        v = td.get(f"{e['season']}|{l['week']}|{l['pid']}")
        status.append("void" if v is None else "W" if v >= 1 else "L")
    actual = [td.get(f"{e['season']}|{l['week']}|{l['pid']}") for l in e["legs"]]
    if "L" in status:
        return actual, "L", -1.0
    if None in status:
        return None
    won = [l for l, s in zip(e["legs"], status) if s == "W"]
    if not won:
        return actual, "void", 0.0
    dec = 1.0
    for l in won:
        dec *= 1 + profit(l["price"])
    return actual, "W", round(dec - 1, 3)


def _settle(e: dict, results: dict):
    """(actual, outcome) for one entry, or None while its game is not final."""
    season, week = e["season"], e["week"]
    if f"{season}|{week}|{e['team']}" not in set(results.get("final") or []):
        return None
    if e["market"] == "TD":
        v = (results.get("td") or {}).get(f"{season}|{week}|{e['pid']}")
        return (None, "void") if v is None else (v, "W" if v >= 1 else "L")
    v = (results.get("y") or {}).get(f"{season}|{week}|{e['pid']}|{e['market']}")
    if v is None:
        return None, "void"
    if v == e["line"]:
        return v, "P"
    won = v > e["line"] if e["side"] == "Over" else v < e["line"]
    return v, "W" if won else "L"


def grade(entries: list, results: dict) -> tuple[list, bool]:
    """(entries with every newly final pick graded, whether anything changed).  Graded entries are left alone."""
    out, changed = [], False
    for e in entries:
        if e.get("outcome") is not None:
            out.append(e)
            continue
        if e.get("kind") == "parlay":
            s = _settle_parlay(e, results)
            if s is None:
                out.append(e)
                continue
            actual, outcome, units = s
        else:
            s = _settle(e, results)
            if s is None:
                out.append(e)
                continue
            actual, outcome = s
            units = round(profit(e["price"]), 3) if outcome == "W" else -1.0 if outcome == "L" else 0.0
        out.append({**e, "actual": actual, "outcome": outcome, "units": units})
        changed = True
    return out, changed


def summary(entries: list) -> dict:
    """Record, units and ROI (units per pick settled, voids excluded), plus pending and void counts."""
    n = {k: sum(e.get("outcome") == k for e in entries) for k in ("W", "L", "P", "void")}
    settled = n["W"] + n["L"] + n["P"]
    units = round(sum(e.get("units") or 0 for e in entries), 3)
    return {"n": len(entries), "w": n["W"], "l": n["L"], "p": n["P"], "void": n["void"],
            "pending": sum(e.get("outcome") is None for e in entries), "units": units,
            "roi": units / settled if settled else None}


def update(ledger_dir, res) -> list:
    """Grade this season's ledger with the build's results; write it back if anything settled.  Returns the entries."""
    path = Path(ledger_dir) / f"{res.season}.json"
    entries = load(path)
    if not entries:
        return []
    entries, changed = grade(entries, res.results or {})
    if changed:
        save(path, entries)
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(prog="props.ledger", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("log", help="log the top N picks of an archived snapshot")
    lg.add_argument("--snapshot", type=Path, required=True)
    lg.add_argument("--top", type=int, default=10)
    lg.add_argument("--parlays", action="store_true", help="log the snapshot's TD parlays instead of its top picks")
    lg.add_argument("--ledger", type=Path, default=Path("history/ledger"))
    sh = sub.add_parser("show", help="print the ledger and its record")
    sh.add_argument("--season", type=int)
    sh.add_argument("--ledger", type=Path, default=Path("history/ledger"))
    a = ap.parse_args(argv)

    if a.cmd == "log":
        snap = json.loads(a.snapshot.read_text())
        now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        new = card_parlays(snap, source=a.snapshot.name) if a.parlays else card(snap, a.top, source=a.snapshot.name)
        added = log(a.ledger / f"{snap['season']}.json", new, logged_at=now)
        print(f"Logged {len(added)} {'parlay' if a.parlays else 'pick'}(s) from {a.snapshot.name} (built {snap.get('built')}) to {a.ledger}/{snap['season']}.json")
        for e in added:
            what = f"{e['side']} {e['line']:g}" if e.get("line") is not None else e["side"]
            print(f"  {e['rank']:>2} {e['grade']} {e['name']:<22} {e['label']:<10} {what:<12} {e['price']:+d}  model {e['p']:.1%}")
        return
    files = [a.ledger / f"{a.season}.json"] if a.season else sorted(a.ledger.glob("*.json"))
    for f in files:
        entries = load(f)
        for name, part in (("picks", [e for e in entries if e.get("kind") != "parlay"]),
                           ("parlays", [e for e in entries if e.get("kind") == "parlay"])):
            if part:
                s = summary(part)
                print(f"{f.name} {name}: {s['w']}-{s['l']}-{s['p']} ({s['units']:+.2f}u), {s['pending']} pending, {s['void']} void")
        for e in entries:
            what = f"{e['side']} {e['line']:g}" if e.get("line") is not None else e["side"]
            res = e["outcome"] or "pending"
            print(f"  wk{e['week']} {e['grade']} {e['name']:<22} {e['label']:<10} {what:<12} {e['price']:+d}  {res}"
                  + (f" ({e['actual']})" if e.get("actual") is not None else ""))


if __name__ == "__main__":
    main()
