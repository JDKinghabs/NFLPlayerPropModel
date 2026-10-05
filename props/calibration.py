"""Turn a point projection into P(over a given line) using empirical error distributions.

props/calibration.json holds, for each sheet and position, quantiles of (actual yards / projection)
from walk-forward backtests (research/calibrate_distribution.py).  P(over L) = 1 - F(L / proj).
The same interpolation is mirrored in the website's JavaScript (props/site.py); keep them in sync.
"""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("calibration.json")
FLOOR, CEIL = 0.02, 0.98


def load(path: Path = PATH) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def cdf(p: list[float], r: list[float], x: float) -> float:
    """P(ratio <= x) by linear interpolation through the (quantile, probability) points."""
    if x <= r[0]:
        return p[0] * x / r[0] if r[0] > 0 else p[0]
    if x >= r[-1]:
        return p[-1] + (1 - p[-1]) * min(1.0, (x - r[-1]) / r[-1])
    for i in range(len(r) - 1):
        if r[i] <= x < r[i + 1]:
            return p[i] + (p[i + 1] - p[i]) * (x - r[i]) / (r[i + 1] - r[i])
    return p[-1]


def p_over(p: list[float], r: list[float], proj: float, line: float) -> float:
    return min(CEIL, max(FLOOR, 1 - cdf(p, r, line / proj)))


def quantiles(ratios, probs) -> dict:
    import numpy as np
    r = np.quantile(np.asarray(ratios, dtype=float), probs)
    return {"p": [round(float(x), 4) for x in probs], "r": [round(float(x), 4) for x in r]}
