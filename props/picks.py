"""Top plays: the model's probability against the DraftKings price, graded, capped and explained.

Candidates are every top-N player on the slate against ANY defense (QB 10 / RB 15 / WR 25: the pool the Over/Under
calibration was fit on, research/calibrate_distribution.py) and every anytime-TD row (RB / WR / TE).  Backups are left out:
their probabilities were off by 10-20 points out of sample, so the model has no business grading them.

For each candidate with a DraftKings line:
  model chance   yardage: P(over the line) from the calibrated error distribution (props/calibration.py); TD: P(anytime TD)
  book chance    the probability the price implies, vig included (so a positive edge is a positive-EV bet)
  edge           model - book, on the better side;  EV = profit per 1 unit staked, on average
  grade          A / B when the edge clears PICK_EDGE for the market (about 1.6x / 1x its calibration error) and EV > 0
Then at most one pick per player, PICK_PER_GAME per game, PICK_MAX in all: A before B, higher EV first.  A thin week shows
fewer picks; the board is never padded.

Players whose game has no DraftKings line yet go on a watchlist with target numbers instead: the model's fair line, the line at
which Over / Under becomes a B-grade bet at -110, and for touchdowns the price at which Yes becomes one.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from . import calibration as CAL
from . import config as C
from .odds import _iso, line_for
from .td import TD_GROUPS, fair_odds

LABEL = {"QB": "Pass yds", "RB": "Rush yds", "WR": "Rec yds", "TD": "Anytime TD"}
BOOK_NAME = {"draftkings": "DraftKings"}


# ---- prices --------------------------------------------------------------------------------------------------------
def implied(price: float) -> float:
    """Probability an American price implies (vig included)."""
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def profit(price: float) -> float:
    """Profit per 1 unit staked if the bet wins."""
    return price / 100 if price > 0 else 100 / -price


def ev(p: float, price: float) -> float:
    return p * profit(price) - (1 - p)


def decimal(price: float) -> float:
    """Decimal odds (stake included) for an American price."""
    return 1 + profit(price)


def american(dec: float) -> int:
    """American price for decimal odds."""
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def price_for(p: float) -> int:
    """The American price that implies probability p."""
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def grade(market: str, edge: float, value: float) -> str | None:
    a, b = C.PICK_EDGE[market]
    if value <= 0:
        return None
    return "A" if edge >= a else "B" if edge >= b else None


# ---- yardage lines from the calibrated distribution -------------------------------------------------------------------
def _p_over(cal: dict, market: str, proj: float, line: float) -> float:
    q = cal["elite"][market]
    return CAL.p_over(q["p"], q["r"], proj, line)


def targets(cal: dict, market: str, proj: float) -> dict:
    """Fair line (50/50) and the lines at which Over / Under become a B-grade bet at -110, all on .5 lines."""
    need = C.BREAK_EVEN + C.PICK_EDGE[market][1]
    grid = [k + 0.5 for k in range(0, int(max(3 * proj, 60)))]
    po = [_p_over(cal, market, proj, L) for L in grid]
    over_at = max((L for L, p in zip(grid, po) if p >= need), default=None)
    under_at = min((L for L, p in zip(grid, po) if 1 - p >= need), default=None)
    fair = min(grid, key=lambda L: abs(_p_over(cal, market, proj, L) - 0.5))
    return {"fair_line": fair, "over_at": over_at, "under_at": under_at}


# ---- reasons -------------------------------------------------------------------------------------------------------
def yard_reasons(r: dict, line: float | None = None) -> list:
    out = [f"proj {r['proj']:.0f}" + (f" vs line {line:g}" if line is not None else "")]
    ypg = r.get("ypg")
    if ypg and abs(r["proj"] / ypg - 1) >= 0.08:
        out.append(f"season {ypg:.0f}/g " + ("(hot start, regresses)" if r["proj"] < ypg else "(model above his average)"))
    beta, rank, vs = r.get("beta"), r.get("opp_rank"), r.get("vs_lg")
    if beta and rank is not None and not pd.isna(rank):
        if rank <= C.WEAK_DEF_N:
            out.append(f"weak D #{int(rank)} ({vs:+.0%})")
        elif rank >= 33 - C.WEAK_DEF_N:
            out.append(f"strong D #{int(rank)} ({vs:+.0%})")
    if abs(r.get("gs_ctx") or 0) >= 0.02:
        out.append(f"game script {r['gs_ctx']:+.0%}")
    if r.get("q_flag"):
        out.append(f"QB {r['q_txt']}")
    return out


def td_reasons(r: dict) -> list:
    out = [f"{r['xtd']:.2f} exp TD/g", f"{r['pg_touch']:.0f} touches/g"]
    if r.get("tt") is not None and not pd.isna(r.get("tt")):
        out.append(f"team total {r['tt']:.1f}")
    if r.get("role_up"):
        out.append("starter out: role may be bigger")
    return out


def _base(r: dict, market: str, kind: str) -> dict:
    return dict(kind=kind, market=market, label=LABEL[market], pid=r["player_id"], name=r["name"], team=r["team"],
                opp_txt=r.get("opp_txt", ""), kick_txt=r.get("kick_txt", ""), kickoff=_iso(r["kickoff"]), week=int(r["week"]),
                game=r.get("game_id") or f"{r['week']}-" + "-".join(sorted([r["team"], str(r.get("opp") or "")])),
                inj=r.get("inj") or "")


# ---- candidates ------------------------------------------------------------------------------------------------------
def yard_candidates(elite_all: dict, lines: dict, cal: dict) -> tuple[list, list]:
    """(priced candidates, unpriced rows) for QB / RB / WR yardage."""
    priced, unpriced = [], []
    for market in ("QB", "RB", "WR"):
        df = elite_all.get(market)
        if df is None or df.empty or market not in cal.get("elite", {}):
            continue
        for r in df.to_dict("records"):
            if (r.get("p_out") or 0) >= C.PICK_MAX_P_OUT or pd.isna(r.get("proj")):
                continue
            ln = line_for(lines, r["player_id"], market, r["kickoff"])
            if ln is None:
                unpriced.append({**r, "_market": market})
                continue
            po = _p_over(cal, market, r["proj"], ln["point"])
            sides = []
            if ln.get("over") is not None and not r.get("q_flag"):          # the QB-out flag rules out an Over on his WRs
                sides.append(("Over", po, ln["over"]))
            if ln.get("under") is not None:
                sides.append(("Under", 1 - po, ln["under"]))
            if not sides:
                continue
            side, p, price = max(sides, key=lambda s: ev(s[1], s[2]))
            e, v = p - implied(price), ev(p, price)
            far = abs(ln["point"] - r["proj"]) > C.PICK_MAX_GAP * r["proj"]        # book far from the model: likely news it lacks
            priced.append({**_base(r, market, "yards"), "side": side, "line": ln["point"], "price": price, "p": p,
                           "implied": implied(price), "edge": e, "ev": v, "fair": fair_odds(p), "proj": float(r["proj"]),
                           "grade": None if far else grade(market, e, v), "reasons": yard_reasons(r, ln["point"]),
                           "book": BOOK_NAME.get(C.ODDS_BOOK, C.ODDS_BOOK), "updated": ln.get("updated")})
    return priced, unpriced


def td_candidates(td: dict, lines: dict) -> tuple[list, list]:
    priced, unpriced = [], []
    for g in TD_GROUPS:
        df = (td or {}).get(g)
        if df is None or df.empty:
            continue
        for r in df.to_dict("records"):
            if (r.get("p_out") or 0) >= C.PICK_MAX_P_OUT:
                continue
            ln = line_for(lines, r["player_id"], "TD", r["kickoff"])
            if ln is None or ln.get("yes") is None:
                unpriced.append(r)
                continue
            p, price = float(r["p_td"]), ln["yes"]
            e, v = p - implied(price), ev(p, price)
            cur = r.get("cur_touch")
            role_ok = cur is not None and not pd.isna(cur) and cur >= C.PICK_TD_MIN_ROLE * r["pg_touch"]
            ok = p >= C.PICK_TD_MIN_P and p <= C.PICK_TD_MAX_RATIO * implied(price) and role_ok     # the guards
            gr = grade("TD", e, v) if ok else None
            priced.append({**_base(r, "TD", "td"), "pos": g, "side": "Yes", "line": None, "price": price, "p": p,
                           "implied": implied(price), "edge": e, "ev": v, "fair": fair_odds(p), "proj": None, "grade": gr, "trusted": ok,
                           "reasons": td_reasons(r), "book": BOOK_NAME.get(C.ODDS_BOOK, C.ODDS_BOOK),
                           "updated": ln.get("updated")})
    return priced, unpriced


def select(cands: list) -> list:
    """Graded candidates only: A before B, then higher EV; one per player, PICK_PER_GAME per game, PICK_MAX in all."""
    ranked = sorted((c for c in cands if c["grade"]), key=lambda c: (c["grade"] != "A", -c["ev"]))
    out, players, per_game = [], set(), Counter()
    for c in ranked:
        if c["pid"] in players or per_game[c["game"]] >= C.PICK_PER_GAME:
            continue
        out.append({**c, "rank": len(out) + 1})
        players.add(c["pid"])
        per_game[c["game"]] += 1
        if len(out) == C.PICK_MAX:
            break
    return out


def watchlist(unpriced_yards: list, unpriced_td: list, lines: dict, cal: dict) -> list:
    """Players in a game where the book has posted NO line for that market yet (e.g. yardage props come later in the week than
    TD props).  If the book has priced the market in that game but not this player, it does not offer him: skipped."""
    priced = {(market, team, pd.Timestamp(ln["kickoff"])) for (_, market), lns in lines.items() for ln in lns
              for team in ln.get("teams") or []}

    def market_priced(market: str, team: str, kick) -> bool:
        k = pd.Timestamp(kick).tz_convert("UTC")
        return any(m == market and t == team and abs(k - pk) <= pd.Timedelta(hours=6) for m, t, pk in priced)

    out = []
    for r in unpriced_yards:
        if market_priced(r["_market"], r["team"], r["kickoff"]):
            continue
        t = targets(cal, r["_market"], float(r["proj"]))
        if r.get("q_flag"):                                   # same rule as the picks: no Over on a WR whose QB may miss
            t["over_at"] = None
        out.append({**_base(r, r["_market"], "yards"), **t, "proj": float(r["proj"]), "reasons": yard_reasons(r),
                    "score": abs(r["proj"] / (r.get("ypg") or r["proj"]) - 1)})
    yards = sorted(out, key=lambda w: -w["score"])[: max(C.WATCH_MAX - 4, 0)]
    tds = []
    for r in sorted(unpriced_td, key=lambda r: -r["p_td"]):
        if market_priced("TD", r["team"], r["kickoff"]) or r["p_td"] < C.PICK_TD_MIN_P:
            continue
        need = r["p_td"] - C.PICK_EDGE["TD"][1]
        tds.append({**_base(r, "TD", "td"), "p": float(r["p_td"]), "fair": fair_odds(float(r["p_td"])),
                    "yes_at": price_for(need) if need > 0 else None, "reasons": td_reasons(r)})
        if len(tds) == C.WATCH_MAX - len(yards):
            break
    return yards + tds


PARLAY_TYPES = ("Best chance", "Balanced", "Best value")


def _letter(x: float, cut: tuple) -> str:
    return "A" if x >= cut[0] else "B" if x >= cut[1] else "C"


def td_parlays(cands: list, legs: int = C.PARLAY_LEGS) -> list:
    """Three TD parlays along the line from likeliest to best value: "Best chance" takes the legs most likely to score,
    "Best value" the legs with the most EV, "Balanced" the best average of the two ranks.  Legs: any anytime-TD price the model
    rates at or above the book (PARLAY_MIN_EDGE, not the Top plays bar) that passes the same guards; every leg from a different
    game (same-game TDs are correlated and books price those parlays differently); two parlays share at most PARLAY_MAX_SHARED
    legs.  Model chance = product of the legs' P(TD); price = product of their decimal odds.  A profile that cannot be filled
    is left out, never padded.  Each parlay is graded twice: hit chance and value (PARLAY_HIT_GRADE / PARLAY_VALUE_GRADE)."""
    pool = [c for c in cands if c["kind"] == "td" and c.get("trusted") and c["edge"] >= C.PARLAY_MIN_EDGE and c["ev"] >= 0]
    if len(pool) < legs:
        return []
    by_p = {c["pid"]: i for i, c in enumerate(sorted(pool, key=lambda c: -c["p"]))}
    by_v = {c["pid"]: i for i, c in enumerate(sorted(pool, key=lambda c: -c["ev"]))}
    order = {"Best chance": lambda c: (-c["p"], -c["ev"]), "Best value": lambda c: (-c["ev"], -c["p"]),
             "Balanced": lambda c: (by_p[c["pid"]] + by_v[c["pid"]], -c["p"])}
    built = {}
    for kind in ("Best chance", "Best value", "Balanced"):          # the two ends first, then the middle between them
        chosen, games = [], set()
        for c in sorted(pool, key=order[kind]):
            if c["game"] in games or any(c["pid"] == x["pid"] for x in chosen):
                continue
            pids = {x["pid"] for x in chosen} | {c["pid"]}
            if any(len(pids & {l["pid"] for l in b["legs"]}) > C.PARLAY_MAX_SHARED for b in built.values()):
                continue
            chosen.append(c)
            games.add(c["game"])
            if len(chosen) == legs:
                break
        if len(chosen) < legs:
            continue
        dec, p = 1.0, 1.0
        for c in chosen:
            dec, p = dec * decimal(c["price"]), p * c["p"]
        ev_ = p * dec - 1
        built[kind] = {"type": kind, "p": p, "dec": dec, "price": american(dec), "implied": 1 / dec, "edge": p - 1 / dec,
                       "ev": ev_, "hit_grade": _letter(p, C.PARLAY_HIT_GRADE), "value_grade": _letter(ev_, C.PARLAY_VALUE_GRADE),
                       "book": chosen[0]["book"],
                       "legs": [{k: c.get(k) for k in ("pid", "name", "team", "pos", "opp_txt", "kick_txt", "kickoff", "week",
                                                       "price", "p", "implied", "edge", "ev", "grade", "inj", "updated")}
                                for c in chosen]}
    return [{**built[k], "rank": i + 1} for i, k in enumerate(t for t in PARLAY_TYPES if t in built)]


def make(elite_all: dict, td: dict, lines: dict, cal: dict | None) -> tuple[list, list]:
    """(picks, watchlist) for the board."""
    if not cal:
        return [], []
    py, uy = yard_candidates(elite_all or {}, lines or {}, cal)
    pt, ut = td_candidates(td, lines or {})
    return select(py + pt), watchlist(uy, ut, lines or {}, cal)
