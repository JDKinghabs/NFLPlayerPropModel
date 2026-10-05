"""Touches outlook for Sheet 1 players: expected attempts / touches / targets, plus a workload flag.

Validated (research/experiment_touches.py, walk-forward 2023-25):
  * QB attempts rise with how many attempts the opposing defense faces (t = 4.1; out-of-sample error -2.9%), so the
    QB expectation uses it.
  * Teammates ruled Out raise RB touches (+19% over 36 games, t = 3.6) and WR targets (+6%, t = 2.8), but the effect is
    rare and noisy and did not improve out-of-sample accuracy, so for RB/WR it is shown as a FLAG with the historical
    size of the bump and is NOT folded into the expected number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .config import Category
from .defense import shrink
from .volume import TOUCH_LABEL, touch_col


def player_touches(stats: pd.DataFrame, prev_stats: pd.DataFrame, cat: Category) -> pd.DataFrame:
    """Per player: season average touches per game, last-3 average, and a baseline shrunk toward last season."""
    def eligible(df):
        s = df[df.position.isin(cat.positions) & (df[cat.volume].fillna(0) > 0)]
        return s.assign(t=touch_col(s, cat.key)).sort_values(["player_id", "week"])
    s = eligible(stats)
    g = s.groupby("player_id")
    out = pd.DataFrame({"t_cur": g.t.mean(), "t_l3": g.t.apply(lambda x: x.tail(3).mean()), "t_games": g.size()})
    prior = pd.Series(dtype=float)
    if prev_stats is not None and len(prev_stats):
        p = eligible(prev_stats).groupby("player_id").t.agg(["mean", "size"])
        prior = p[p["size"] >= C.MIN_PRIOR_GAMES]["mean"]
    out["t_base"] = [shrink(x, n, prior.get(pid, np.nan), C.PLAYER_PRIOR_GAMES)
                     for pid, x, n in zip(out.index, out.t_cur, out.t_games)]
    return out.reset_index()


def vacated_share(stats: pd.DataFrame, cat_key: str, team: str, absent: dict, exclude=None):
    """Share of the team's relevant touch pool held by teammates who may miss the game, weighted by P(out).

    RB: share of RB/FB touches.  WR: share of all team targets.  QB: not used.
    Returns (expected share, [(player_id, name, p_out, share), ...] sorted by impact).
    """
    if cat_key == "QB":
        return 0.0, []
    st = stats[stats.team == team]
    if cat_key == "RB":
        st = st[st.position.isin(["RB", "FB"])]
    st = st.assign(t=touch_col(st, cat_key))
    tot = st.t.sum()
    if tot <= 0:
        return 0.0, []
    share = st.groupby("player_id").t.sum() / tot
    names = st.groupby("player_id").player_display_name.last()
    items = [(pid, names.get(pid, pid), p, float(share.get(pid, 0.0))) for pid, p in absent.items()
             if pid != exclude and share.get(pid, 0.0) > 0]
    items.sort(key=lambda x: -x[2] * x[3])
    return float(sum(p * sh for _, _, p, sh in items)), items


def add_outlook(m: pd.DataFrame, cat: Category, stats, prev_stats, ratings: pd.DataFrame, pout_by_week: dict) -> pd.DataFrame:
    """Attach t_* columns to Sheet 1 rows (needs player_id, team, opp, week)."""
    cols = ["t_cur", "t_l3", "t_base", "t_fvol", "t_exp", "t_vac", "t_out", "t_flag", "t_if"]
    if m.empty:
        return m.assign(**{c: pd.Series(dtype=float) for c in cols}, t_label=TOUCH_LABEL[cat.key])
    m = m.merge(player_touches(stats, prev_stats, cat)[["player_id", "t_cur", "t_l3", "t_base"]], on="player_id", how="left")
    vf = ratings.set_index("defense")["vol_factor"] if "vol_factor" in ratings else pd.Series(dtype=float)
    m["t_fvol"] = m.opp.map(vf)
    beta = C.TOUCH_QB_VOLUME_BETA if cat.key == "QB" else 0.0
    m["t_exp"] = m.t_base * (1 + beta * (m.t_fvol.fillna(1.0) - 1))

    wl = C.TOUCH_WORKLOAD.get(cat.key)
    vac, out, flag, t_if = [], [], [], []
    for pid, team, wk, base in zip(m.player_id, m.team, m.week, m.t_base):
        v, items, txt, fl, tif = 0.0, [], "", False, np.nan
        po = pout_by_week.get(wk)
        if wl and po is not None and len(po):
            ab = po[(po.source == "injury") & (po.p_out > 0)] if "source" in po else po[po.p_out > 0]
            labels = dict(zip(ab.gsis_id, ab.label))
            v, items = vacated_share(stats, cat.key, team, dict(zip(ab.gsis_id, ab.p_out)), exclude=pid)
            txt = "; ".join(f"{n} {labels.get(i, '')} ({sh:.0%} of {'RB touches' if cat.key == 'RB' else 'targets'})"
                            for i, n, p, sh in items[:3])
            fl = v >= C.TOUCH_FLAG_MIN
            tif = base * (1 + wl["slope"] * v / (1 - min(v, 0.7))) if fl else np.nan
        vac.append(v); out.append(txt if fl else ""); flag.append(fl); t_if.append(tif)
    m["t_vac"], m["t_out"], m["t_flag"], m["t_if"] = vac, out, flag, t_if
    m["t_label"] = TOUCH_LABEL[cat.key]
    return m
