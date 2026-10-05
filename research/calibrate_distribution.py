"""Fit the error distributions behind the site's P(over) and check them out of sample.

  Elite sheet : ratio = actual yards / projection for the walk-forward top-10 players (2023-25).
  Backups     : ratio = actual yards / "Proj if Out" for backups whose starter was listed Out and who
                played (2024-25).

Writes props/calibration.json.  Elite is checked on a 2025 hold-out (fit on 2023-24); backups, with far
fewer rows, are checked fit-2024 -> test-2025 and the shipped file uses both seasons.

    python research/calibrate_distribution.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import backtest_backups as BB                                   # noqa: E402
import backtest_elite as BE                                     # noqa: E402
from props import calibration as CAL                            # noqa: E402
from props import config as C                                   # noqa: E402

warnings.filterwarnings("ignore")
P_ELITE = [round(i / 20, 2) for i in range(1, 20)]              # 5% .. 95%
P_BACKUP = [round(i / 10, 2) for i in range(1, 10)]             # 10% .. 90%
LINES = (0.8, 0.9, 1.0, 1.1, 1.2)


def elite_rows(season, cat):
    df = BE.run(season, cat, C.PLAYER_PRIOR_GAMES, C.DEF_PRIOR_GAMES, C.DEF_PRIOR_REGRESS)
    df["proj"] = BE.add_projection(df, C.ELITE_GROUP_PULL, C.MATCHUP_BETA)
    return df.assign(ratio=df.y / df.proj)


def check(q, ratios, label):
    """Predicted vs realised P(over) at lines of 80-120% of the projection, on the test rows."""
    ratios = np.asarray(ratios)
    parts = []
    for m in LINES:
        pred = 1 - CAL.cdf(q["p"], q["r"], m)
        parts.append(f"{m:.1f}x: pred {pred:.2f} / actual {np.mean(ratios > m):.2f}")
    print(f"  {label:34s} n={len(ratios):4d} | " + " | ".join(parts))


def main():
    out = {"version": pd.Timestamp.now().strftime("%Y-%m-%d"),
           "note": "quantiles of actual/projection from walk-forward backtests; see research/calibrate_distribution.py",
           "elite": {}, "backup": {}, "n": {}}

    print("== Elite sheet: fit 2023-24, test 2025 ==")
    for k, cat in C.CATS.items():
        tr = pd.concat([elite_rows(s, cat) for s in (2023, 2024)]).ratio
        te = elite_rows(2025, cat).ratio
        check(CAL.quantiles(tr, P_ELITE), te, f"{k} (hold-out)")
        allr = pd.concat([tr, te])
        out["elite"][k] = CAL.quantiles(allr, P_ELITE)
        out["n"][f"elite_{k}"] = int(len(allr))

    print("\n== Backups: fit 2024, test 2025 (small samples) ==")
    b24, b25 = BB.run(2024), BB.run(2025)
    for k in C.CATS:
        def rr(d):
            d = d[(d.cat == k) & (d.act_vol > 0) & (d.proj_yds > 0)]
            return (d.act_yds / d.proj_yds)
        tr, te = rr(b24), rr(b25)
        if len(tr) >= 15 and len(te) >= 15:
            check(CAL.quantiles(tr, P_BACKUP), te, f"{k} (fit 2024 -> 2025)")
        allr = pd.concat([tr, te])
        out["backup"][k] = CAL.quantiles(allr, P_BACKUP)
        out["n"][f"backup_{k}"] = int(len(allr))

    CAL.PATH.write_text(json.dumps(out, indent=1))
    print(f"\nWrote {CAL.PATH}  rows used: {out['n']}")
    for sheet in ("elite", "backup"):
        for k, q in out[sheet].items():
            mid = q["r"][len(q["r"]) // 2]
            print(f"  {sheet:6s} {k}: median actual/proj = {mid:.2f}  (10th pct {q['r'][0]:.2f}, 90th/95th pct {q['r'][-1]:.2f})")


if __name__ == "__main__":
    main()
