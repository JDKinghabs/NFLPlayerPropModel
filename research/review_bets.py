"""Review an exported bet log against actual results and say whether the model needs retuning.

    python research/review_bets.py nfl-prop-bets.json                  # results pulled from nflverse
    python research/review_bets.py nfl-prop-bets.json --results site/results.json

Export the file from the "My bets" tab ("Export bets").  Every bet carries the frozen pre-game snapshot, so this
compares what the model said then with what happened, never with anything learned afterward.

The recommendations are deliberately conservative: nothing is suggested until a position has 30+ settled bets and the
95% interval on the model's bias excludes zero by a meaningful margin.  Fewer bets than that is mostly noise.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_N_FOR_ADVICE = 30
MIN_BIAS_FOR_ADVICE = 0.03


def grade(bet: dict, results: dict) -> dict:
    """Mirror of the website's grading: pending / void / push / win / loss, with profit in units."""
    if f'{bet["season"]}|{bet["week"]}|{bet["team"]}' not in set(results["final"]):      # keys carry the season
        return {"s": "pending"}
    actual = results["y"].get(f'{bet["season"]}|{bet["week"]}|{bet["pid"]}|{bet["cat"]}')
    if actual is None:
        return {"s": "void", "profit": 0.0}
    if actual == bet["line"]:
        return {"s": "push", "actual": actual, "profit": 0.0}
    won = (bet["side"] == "Over") == (actual > bet["line"])
    odds = bet["odds"]
    win_amt = bet["stake"] * (odds / 100 if odds > 0 else 100 / abs(odds))
    return {"s": "win" if won else "loss", "actual": actual, "profit": win_amt if won else -bet["stake"]}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def analyze(bets: list[dict], results: dict) -> dict:
    rows = [(b, grade(b, results)) for b in bets]
    settled = [(b, g) for b, g in rows if g["s"] in ("win", "loss", "push")]
    out = {"n_bets": len(bets), "pending": sum(g["s"] == "pending" for _, g in rows),
           "void": sum(g["s"] == "void" for _, g in rows), "settled": len(settled),
           "models": defaultdict(int), "groups": {}, "calibration": [], "lean": {}, "advice": []}
    for b, _ in rows:
        out["models"][b.get("model", "v1")] += 1
    out["models"] = dict(out["models"])

    def record(sub):
        w = sum(g["s"] == "win" for _, g in sub); l = sum(g["s"] == "loss" for _, g in sub)
        staked = sum(b["stake"] for b, g in sub if g["s"] != "push")
        profit = sum(g["profit"] for _, g in sub)
        return {"w": w, "l": l, "p": len(sub) - w - l, "units": profit, "roi": profit / staked if staked else 0.0}
    out["overall"] = record(settled)

    # model accuracy by (sheet, position): actual / frozen projection - 1
    by = defaultdict(list)
    for b, g in settled:
        sn = b.get("snap") or {}
        if sn.get("proj", 0) > 0:
            by[(b["sheet"], b["cat"])].append((g["actual"] / sn["proj"] - 1, abs(g["actual"] - sn["proj"])))
    for key, vals in sorted(by.items()):
        r = np.array([v[0] for v in vals]); n = len(r)
        mean = float(r.mean()); se = float(r.std(ddof=1) / math.sqrt(n)) if n > 1 else float("inf")
        lo, hi = mean - 1.96 * se, mean + 1.96 * se
        out["groups"][key] = {"n": n, "bias": mean, "lo": lo, "hi": hi, "mae": float(np.mean([v[1] for v in vals]))}
        if n < MIN_N_FOR_ADVICE:
            out["advice"].append(f"{key[0]}/{key[1]}: {n} settled bets, need {MIN_N_FOR_ADVICE}+ before suggesting anything.")
        elif (lo > 0 or hi < 0) and abs(mean) >= MIN_BIAS_FOR_ADVICE:
            out["advice"].append(f"{key[0]}/{key[1]}: projections ran {mean:+.0%} vs actual (95% CI {lo:+.0%} to {hi:+.0%}, n={n}). "
                                 f"Consider a level adjustment of about {-mean:+.0%} (research/backtest_*.py can confirm on history first).")
        else:
            out["advice"].append(f"{key[0]}/{key[1]}: bias {mean:+.0%} (95% CI {lo:+.0%} to {hi:+.0%}, n={n}): no change warranted.")

    # touches forecast (attempts / touches / targets) vs actual, for bets whose snapshot carries one
    tby = defaultdict(list)
    for b, g in rows:
        te = (b.get("snap") or {}).get("t_exp")
        act = results.get("t", {}).get(f'{b["season"]}|{b["week"]}|{b["pid"]}|{b["cat"]}')
        if te and act is not None and g["s"] in ("win", "loss", "push"):
            tby[b["cat"]].append(act / te - 1)
    out["touches"] = {k: {"n": len(v), "bias": float(np.mean(v))} for k, v in tby.items()}

    # calibration of the Over probability (elite bets only, pushes excluded)
    cal = [(b["pOver"], g["actual"] > b["line"]) for b, g in settled if b.get("pOver") is not None and g["s"] != "push"]
    for lo_, hi_, label in ((0, .35, "<35%"), (.35, .45, "35-45%"), (.45, .55, "45-55%"), (.55, .65, "55-65%"), (.65, 1.01, "65%+")):
        g_ = [(p, hit) for p, hit in cal if lo_ <= p < hi_]
        if g_:
            k = sum(hit for _, hit in g_); n = len(g_); wl, wh = wilson(k, n)
            out["calibration"].append({"bucket": label, "n": n, "said": float(np.mean([p for p, _ in g_])), "hit": k / n, "lo": wl, "hi": wh})

    # did following the model's lean beat going against it?
    for name, pick in (("followed", lambda b: b["side"] == b.get("lean")), ("against", lambda b: b.get("lean") in ("Over", "Under") and b["side"] != b["lean"])):
        sub = [(b, g) for b, g in settled if b.get("lean") in ("Over", "Under") and g["s"] != "push" and pick(b)]
        w = sum(g["s"] == "win" for _, g in sub); n = len(sub)
        out["lean"][name] = {"n": n, "w": w, "rate": w / n if n else None, "ci": wilson(w, n) if n else None}
    return out


def print_report(a: dict) -> None:
    o = a["overall"]
    print(f"Bets: {a['n_bets']}  (settled {a['settled']}, pending {a['pending']}, void {a['void']})   models: {a['models']}")
    print(f"Record {o['w']}-{o['l']}-{o['p']}   units {o['units']:+.2f}   ROI {o['roi']:+.1%}")
    if a["settled"] < 100:
        print(f"-> only {a['settled']} settled bets; results this small are mostly luck. Treat as a diary.")
    print("\nModel vs actual (actual / frozen projection - 1):")
    for (sheet, cat), g in a["groups"].items():
        print(f"  {sheet:7s} {cat}: n={g['n']:3d}  bias {g['bias']:+.1%}  95% CI [{g['lo']:+.1%}, {g['hi']:+.1%}]  avg miss {g['mae']:.0f} yds")
    for k, t in a.get("touches", {}).items():
        print(f"\nTouches forecast, {k}: n={t['n']}  actual vs expected {t['bias']:+.1%}")
    if a["calibration"]:
        print("\nWhen the model said X% Over, how often did it go Over?")
        for c in a["calibration"]:
            print(f"  {c['bucket']:7s} n={c['n']:3d}  said {c['said']:.0%}  happened {c['hit']:.0%}  (95% CI {c['lo']:.0%}-{c['hi']:.0%})")
    for name, l in a["lean"].items():
        if l["n"]:
            print(f"\nBets {name} the model's lean: {l['w']}-{l['n'] - l['w']}  ({l['rate']:.0%}, 95% CI {l['ci'][0]:.0%}-{l['ci'][1]:.0%})")
    print("\nAdvice:")
    for line in a["advice"] or ["(no graded bets yet)"]:
        print("  -", line)


def load_results(bets: list[dict], path: Path | None) -> dict:
    if path:
        return json.loads(Path(path).read_text())
    from props.data import cached, STAT_COLS
    from props.results import build_results
    import pandas as pd
    final, y, tt, season = [], {}, {}, None
    for s in sorted({b["season"] for b in bets}):
        d = pd.read_csv(cached(f"stats_player/stats_player_week_{s}.csv", True), usecols=lambda c: c in STAT_COLS)
        r = build_results(d[d.season_type == "REG"], s)
        final += r["final"]; y.update(r["y"]); tt.update(r["t"]); season = s
    return {"season": season, "final": final, "y": y, "t": tt}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bets", type=Path, help="exported nfl-prop-bets.json")
    ap.add_argument("--results", type=Path, help="results.json from the site (default: build from nflverse)")
    a = ap.parse_args()
    bets = json.loads(a.bets.read_text())
    print_report(analyze(bets, load_results(bets, a.results)))


if __name__ == "__main__":
    main()
