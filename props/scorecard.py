"""Scorecard: grade the frozen pre-game predictions in history/ against what actually happened.

    python -m props.scorecard [--history history] [--season 2026] [--out scorecard.json]

For every player-week the LATEST snapshot holding it is graded (a snapshot only holds games that had not kicked off, so that is
the last thing the model said before kickoff).  A game counts once its team-week is final in props/results.py's `final` list; a
player with no stat line that week did not play and is left out (void), the same rule the site uses for logged bets.

Three reports:
  td      anytime-TD probability vs whether he scored a rushing or receiving TD: log loss and Brier against always-guessing-the-
          base-rate, plus predicted vs actual rate by probability bucket.
  yards   Sheet 1 (elite) and Sheet 2 (backup) yardage projections vs actual yards: bias, MAE, RMSE per position.
  qb      the QB-out flag: how often a flagged team's starter really missed, and how WRs did against their projection then.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .qbout import starter_qb
from .results import build_results

TD_BUCKETS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.01]


def load_latest(root, season: int) -> dict:
    """Last pre-kickoff row for each player-week, as {"td": [...], "elite": [...], "backup": [...]}."""
    out = {"td": {}, "elite": {}, "backup": {}}
    d = Path(root) / str(season)
    for path in sorted(d.glob("*.json")) if d.exists() else []:       # file names sort by build time, so later files overwrite
        snap = json.loads(path.read_text())
        for kind in out:
            for r in snap.get(kind, []):
                out[kind][(r["week"], r["pid"], r.get("cat", ""))] = {**r, "snapshot": path.name}
    return {k: list(v.values()) for k, v in out.items()}


def _played(stats: pd.DataFrame, season: int) -> dict:
    """{(week, player_id): row} for every stat line, plus the set of final (week, team)."""
    s = stats[stats.season == season]
    final = {(int(w), t) for w, t in zip(s.week, s.team)}
    lines = {(int(r.week), r.player_id): r for r in s.itertuples()}
    return {"lines": lines, "final": final, "stats": s}


def _td_actual(r) -> int:
    return int((np.nan_to_num(r.rushing_tds) + np.nan_to_num(r.receiving_tds)) > 0)


def grade_td(rows: list, g: dict) -> dict:
    graded = []
    for r in rows:
        line = g["lines"].get((r["week"], r["pid"]))
        if line is not None and r["p_td"] is not None:
            graded.append((r["pos"], float(r["p_td"]), _td_actual(line)))
    if not graded:
        return {"n": 0}

    def summarise(items) -> dict:
        p = np.clip(np.array([x[1] for x in items]), 1e-4, 1 - 1e-4)
        y = np.array([x[2] for x in items])
        base = np.clip(y.mean(), 1e-4, 1 - 1e-4)
        ll = lambda q: float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
        out = {"n": len(items), "predicted": round(float(p.mean()), 4), "actual": round(float(y.mean()), 4),
               "log_loss": round(ll(p), 4), "log_loss_base_rate": round(ll(base), 4),
               "brier": round(float(np.mean((p - y) ** 2)), 4), "brier_base_rate": round(float(np.mean((base - y) ** 2)), 4)}
        idx = np.digitize(p, TD_BUCKETS) - 1
        out["buckets"] = [{"range": f"{TD_BUCKETS[b]:.0%}-{min(TD_BUCKETS[b + 1], 1):.0%}", "n": int((idx == b).sum()),
                           "predicted": round(float(p[idx == b].mean()), 4), "actual": round(float(y[idx == b].mean()), 4)}
                          for b in range(len(TD_BUCKETS) - 1) if (idx == b).any()]
        return out

    res = {"all": summarise(graded)}
    for pos in sorted({x[0] for x in graded}):
        res[pos] = summarise([x for x in graded if x[0] == pos])
    return res


def grade_yards(rows: list, g: dict) -> dict:
    out = {}
    for cat, spec in C.CATS.items():
        err = []
        for r in rows:
            if r.get("cat") != cat:
                continue
            line = g["lines"].get((r["week"], r["pid"]))
            proj = r.get("proj", r.get("proj_exp"))
            if line is None or proj is None:
                continue
            err.append(float(np.nan_to_num(getattr(line, spec.yards))) - float(proj))      # actual - projected
        if err:
            e = np.array(err)
            out[cat] = {"n": len(e), "bias": round(float(e.mean()), 1), "mae": round(float(np.abs(e).mean()), 1),
                        "rmse": round(float(math.sqrt((e ** 2).mean())), 1)}
    return out


def grade_qb(elite: list, g: dict) -> dict:
    """Did the flagged teams' starters actually miss, and how did their WRs do against projection?"""
    stats = g["stats"]
    miss = {}
    for r in elite:
        key = (r["week"], r["team"])
        if key in miss or key not in g["final"]:
            continue
        s = starter_qb(stats, r["team"], r["week"])
        if s is None:
            continue
        att = stats[(stats.week == r["week"]) & (stats.player_id == s[0])].attempts.fillna(0).sum()
        miss[key] = (bool(r["qb_flag"]), r["qb_p"] or 0.0, att <= 0)
    flagged = [v for v in miss.values() if v[0]]
    rest = [v for v in miss.values() if not v[0]]
    out = {"team_games_flagged": len(flagged), "team_games_unflagged": len(rest)}
    if flagged:
        out["flagged_qb_missed"] = round(float(np.mean([v[2] for v in flagged])), 3)
        out["flagged_mean_p_out"] = round(float(np.mean([v[1] for v in flagged])), 3)
    if rest:
        out["unflagged_qb_missed"] = round(float(np.mean([v[2] for v in rest])), 3)
    wr = {True: [], False: []}
    for r in elite:
        if r.get("cat") != "WR" or (r["week"], r["team"]) not in miss:
            continue
        line = g["lines"].get((r["week"], r["pid"]))
        if line is not None:
            wr[bool(r["qb_flag"])].append(float(np.nan_to_num(line.receiving_yards)) - float(r["proj"]))
    for flag, name in ((True, "wr_flagged"), (False, "wr_unflagged")):
        if wr[flag]:
            out[name] = {"n": len(wr[flag]), "mean_actual_minus_proj": round(float(np.mean(wr[flag])), 1)}
    return out


def scorecard(root, stats: pd.DataFrame, season: int) -> dict:
    latest = load_latest(root, season)
    g = _played(stats, season)
    final = {tuple(k.split("|")[1:]) for k in build_results(stats, season)["final"]}      # (week, team) as strings
    final = {(int(w), t) for w, t in final}
    g["final"] = final
    keep = lambda rows: [r for r in rows if (r["week"], r["team"]) in final]              # game is over
    td, elite, backup = (keep(latest[k]) for k in ("td", "elite", "backup"))
    return {"season": season, "weeks_graded": sorted({r["week"] for r in td + elite + backup}),
            "td": grade_td(td, g), "yards": {"elite": grade_yards(elite, g), "backup": grade_yards(backup, g)},
            "qb": grade_qb(elite, g)}


def render(sc: dict) -> str:
    if not sc["weeks_graded"]:
        return f"{sc['season']}: nothing to grade yet (no archived prediction belongs to a finished game)."
    L = [f"Scorecard {sc['season']}, weeks {', '.join(map(str, sc['weeks_graded']))}", "", "Anytime TD (lower log loss / Brier is better)"]
    for pos, s in sc["td"].items():
        if not s.get("n"):
            continue
        L.append(f"  {pos:<4} n={s['n']:<4} predicted {s['predicted']:.1%}  actual {s['actual']:.1%}  log loss {s['log_loss']:.3f} "
                 f"(base rate {s['log_loss_base_rate']:.3f})  Brier {s['brier']:.3f} (base rate {s['brier_base_rate']:.3f})")
    if sc["td"].get("all", {}).get("buckets"):
        L.append("  by probability:  " + "   ".join(f"{b['range']}: {b['actual']:.0%} of {b['n']} (said {b['predicted']:.0%})"
                                                    for b in sc["td"]["all"]["buckets"]))
    L += ["", "Yardage projections (actual minus projected, yards)"]
    for sheet in ("elite", "backup"):
        for cat, s in sc["yards"][sheet].items():
            L.append(f"  {sheet:<6} {cat}  n={s['n']:<4} bias {s['bias']:+.1f}  MAE {s['mae']:.1f}  RMSE {s['rmse']:.1f}")
    q = sc["qb"]
    L += ["", "QB-out flag", f"  flagged team-games {q['team_games_flagged']}, unflagged {q['team_games_unflagged']}"]
    if "flagged_qb_missed" in q:
        L.append(f"  flagged: starter missed {q['flagged_qb_missed']:.0%} (flag said {q['flagged_mean_p_out']:.0%} on average); "
                 f"unflagged: {q.get('unflagged_qb_missed', 0):.0%}")
    for k in ("wr_flagged", "wr_unflagged"):
        if k in q:
            L.append(f"  {k}: n={q[k]['n']}, actual minus projection {q[k]['mean_actual_minus_proj']:+.1f} yds")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="props.scorecard", description=__doc__.split("\n")[0])
    ap.add_argument("--history", type=Path, default=Path("history"))
    ap.add_argument("--season", type=int)
    ap.add_argument("--out", type=Path, help="also write the numbers as JSON")
    ap.add_argument("--refresh", action="store_true", help="re-download results now")
    a = ap.parse_args(argv)
    from .data import current_season, load_all
    season = a.season or current_season()
    sc = scorecard(a.history, load_all(season, refresh=a.refresh)["stats"], season)
    print(render(sc))
    if a.out:
        a.out.write_text(json.dumps(sc, indent=1) + "\n")


if __name__ == "__main__":
    main()
