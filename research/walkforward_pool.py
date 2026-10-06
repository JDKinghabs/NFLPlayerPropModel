"""Shared walk-forward builders for the pass-catcher experiments (experiment_qb_out.py, experiment_role_features.py).

Everything here uses only information available before each game, the same discipline as backtest_elite.py:
  pool()        top-N at a position by season-to-date yards, with a shrunk per-game baseline for each outcome stat
  qb_context()  per team-week: the QB the team would be expected to start, whether he actually threw, and his
                pre-game injury-report status
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from props import config as C                       # noqa: E402
from props.data import cached                       # noqa: E402
from props.defense import shrink                    # noqa: E402

warnings.filterwarnings("ignore")

COLS = ["player_id", "player_display_name", "position", "team", "opponent_team", "season", "week", "season_type",
        "attempts", "carries", "targets", "receptions", "passing_yards", "rushing_yards", "receiving_yards",
        "receiving_air_yards", "target_share", "air_yards_share", "wopr"]
SEASONS = (2022, 2023, 2024, 2025)
P_OUT_BY_STATUS = {"Out": 1.0, "Doubtful": 1.0, "Questionable": C.P_OUT_QUESTIONABLE_QB}

_STATS: dict = {}


def stats(year: int) -> pd.DataFrame:
    if year not in _STATS:
        d = pd.read_csv(cached(f"stats_player/stats_player_week_{year}.csv", False),
                        usecols=lambda c: c in COLS, low_memory=False)
        _STATS[year] = d[d.season_type == "REG"].copy()
    return _STATS[year]


def injuries(year: int) -> pd.DataFrame:
    p = cached(f"injuries/injuries_{year}.csv", False, required=False)
    d = pd.read_csv(p, low_memory=False) if p else pd.DataFrame()
    return d[d.game_type.fillna("REG") == "REG"] if "game_type" in d else d


def qb_context(season: int) -> pd.DataFrame:
    """One row per team-week with a quarterback history (weeks 2+).

    starter      the QB with the most attempts for the team in earlier games this season
    starter_out  True when he threw under half of the team's attempts in this game (out, or hurt early)
    streak       consecutive earlier team games he did not play (0 = he played last time)
    status/p_out his pre-game injury-report designation for this week and the matching P(out)
                (Out/Doubtful 1.0, Questionable at the calibrated QB rate, otherwise 0)
    p_fresh      p_out only when he played last time (streak 0).  A longer absence is already inside the season
                 averages the projections are built from, so only a *first* missed game is news to the baseline
    first_out    starter_out and streak == 0 (ex-post version of p_fresh)
    """
    s = stats(season)
    q = s[(s.position == "QB") & (s.attempts.fillna(0) > 0)]
    per = q.groupby(["team", "week", "player_id"]).attempts.sum().reset_index()
    inj = injuries(season)
    status = {}
    if len(inj):
        for r in inj[["gsis_id", "week", "report_status"]].dropna().itertuples():
            status[(r.gsis_id, r.week)] = r.report_status
    rows = []
    for team, g in per.groupby("team"):
        weeks = sorted(g.week.unique())
        for w in weeks:
            hist = g[g.week < w]
            if hist.empty:
                continue
            starter = hist.groupby("player_id").attempts.sum().idxmax()
            cur = g[g.week == w].set_index("player_id").attempts
            share = float(cur.get(starter, 0.0)) / float(cur.sum())
            streak = 0
            for pw in sorted((x for x in weeks if x < w), reverse=True):
                if g[(g.week == pw) & (g.player_id == starter)].attempts.sum() > 0:
                    break
                streak += 1
            st = status.get((starter, w), "")
            p_out = P_OUT_BY_STATUS.get(st, 0.0)
            rows.append(dict(season=season, team=team, week=w, starter=starter, share=share,
                             starter_out=share < 0.5, streak=streak, status=st, p_out=p_out,
                             p_fresh=p_out if streak == 0 else 0.0, first_out=bool(share < 0.5 and streak == 0)))
    return pd.DataFrame(rows)


def pool(season: int, positions: tuple, topn: int, outcomes: list, vol_col: str, rank_col: str,
         extra: tuple = (), start_wk: int = 4) -> pd.DataFrame:
    """Walk-forward rows: for each week >= start_wk, the top-N players at `positions` by season-to-date `rank_col`
    who played that week with `vol_col` > 0.

    For each outcome o: actual `o`, shrunk baseline `base_o` (season average pulled toward last season and toward the
    pool mean, as production does), plus `ytd_o` / `l3_o`.  `extra` columns get `ytd_*` / `l3_*` features too.
    """
    cur, prev = stats(season), stats(season - 1)
    c = cur[cur.position.isin(positions) & (cur[vol_col].fillna(0) > 0)]
    p = prev[prev.position.isin(positions) & (prev[vol_col].fillna(0) > 0)]
    prior = {o: p.groupby("player_id")[o].agg(["mean", "size"]) for o in outcomes}
    rows = []
    for w in range(start_wk, int(cur.week.max()) + 1):
        tgt, hist = c[c.week == w], c[c.week < w]
        if tgt.empty:
            continue
        top = hist.groupby("player_id")[rank_col].sum().sort_values(ascending=False).head(topn).index
        for prank, pid in enumerate(top, 1):
            t = tgt[tgt.player_id == pid]
            if t.empty:
                continue
            t = t.iloc[0]
            h = hist[hist.player_id == pid].sort_values("week")
            r = dict(season=season, week=w, pid=pid, name=t.player_display_name, team=t.team, opp=t.opponent_team,
                     prank=prank, n=len(h))
            for o in outcomes:
                pr = prior[o]
                pm = pr.loc[pid, "mean"] if pid in pr.index and pr.loc[pid, "size"] >= C.MIN_PRIOR_GAMES else h[o].mean()
                r[o] = t[o]
                r["base_" + o] = shrink(h[o].mean(), len(h), pm, C.PLAYER_PRIOR_GAMES)
                r["ytd_" + o], r["l3_" + o] = h[o].mean(), h[o].tail(3).mean()
            for e in extra:
                r["ytd_" + e], r["l3_" + e] = h[e].mean(), h[e].tail(3).mean()
                r["sum_" + e] = h[e].sum()
            rows.append(r)
    df = pd.DataFrame(rows)
    for o in outcomes:                                   # winner's-curse pull toward the week's pool mean
        gm = df.groupby("week")["base_" + o].transform("mean")
        df["base_" + o] = (1 - C.ELITE_GROUP_PULL) * df["base_" + o] + C.ELITE_GROUP_PULL * gm
    return df


def ols(X: np.ndarray, y: np.ndarray, cluster=None):
    """Coefficients and t-stats (intercept first).

    Heteroskedasticity-robust by default; pass `cluster` (one label per row) for cluster-robust standard errors.
    Use it whenever several rows share one underlying event, e.g. every receiver in a game whose QB is out.
    """
    X = np.column_stack([np.ones(len(X)), X])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    xtx = np.linalg.pinv(X.T @ X)
    n, k = X.shape
    if cluster is None:
        meat = (X.T * (e ** 2)) @ X
        scale = n / (n - k)
    else:
        codes = pd.factorize(np.asarray(cluster))[0]
        sg = np.zeros((codes.max() + 1, k))
        np.add.at(sg, codes, X * e[:, None])
        meat = sg.T @ sg
        g = codes.max() + 1
        scale = g / (g - 1) * (n - 1) / (n - k)
    cov = xtx @ meat @ xtx * scale
    return b, b / np.sqrt(np.diag(cov))


def rmse(e) -> float:
    return float(np.sqrt(np.mean(np.asarray(e, dtype=float) ** 2)))


P_OUT_SKILL = {"Out": 1.0, "Doubtful": 1.0, "Questionable": C.P_OUT_QUESTIONABLE}


def absences(season: int, kind: str, min_games: int = 2) -> pd.DataFrame:
    """Key teammates who are (or may be) missing, one row per (team, week, player), weeks 4+.

    kind "targets": WR/TE/RB holding at least the WR starter share of the team's targets in the games they played
         "rb":      RB/FB holding at least the RB starter share of the team's RB carries
    (the same thresholds and share definition props/backups.py uses to decide who counts as a starter).
    Columns: share, status / p_out (pre-game injury report; Out/Doubtful 1.0, Questionable at the calibrated rate),
    streak (consecutive earlier team games he did not play; 0 = he played last time), ex_out (no volume in the game).
    """
    s = stats(season)
    if kind == "rb":
        s = s[s.position.isin(["RB", "FB"])]
        vol, floor, cands = "carries", C.CATS["RB"].starter_min_share, {"RB", "FB"}
    else:
        vol, floor, cands = "targets", C.CATS["WR"].starter_min_share, {"WR", "TE", "RB", "FB"}
    s = s.assign(v=s[vol].fillna(0))
    inj = injuries(season)
    status = {}
    if len(inj):
        for r in inj[["gsis_id", "week", "report_status"]].dropna().itertuples():
            status[(r.gsis_id, r.week)] = r.report_status
    rows = []
    for team, sub in s.groupby("team"):
        mat = sub.pivot_table(index="week", columns="player_id", values="v", aggfunc="sum").fillna(0.0)
        tot = mat.sum(axis=1)
        pos = sub.groupby("player_id").position.last()
        for w in (x for x in mat.index if x >= 4):
            hist = mat[mat.index < w]
            for pid in mat.columns:
                if pos.get(pid) not in cands:
                    continue
                act = hist.index[hist[pid] > 0]
                if len(act) < min_games:
                    continue
                share = float(hist.loc[act, pid].sum() / tot.loc[act].sum())
                if share < floor:
                    continue
                st = status.get((pid, w), "")
                p_out, ex_out = P_OUT_SKILL.get(st, 0.0), bool(mat.loc[w, pid] <= 0)
                if p_out == 0 and not ex_out:
                    continue
                streak = 0
                for pw in sorted(hist.index, reverse=True):
                    if hist.loc[pw, pid] > 0:
                        break
                    streak += 1
                rows.append(dict(season=season, team=team, week=w, pid=pid, share=share, status=st, p_out=p_out,
                                 streak=streak, ex_out=ex_out))
    return pd.DataFrame(rows)
