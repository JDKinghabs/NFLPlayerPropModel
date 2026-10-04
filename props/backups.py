"""Sheet 2: backups who inherit volume because a starter is out (or might be).

Method, per team and position group, for one upcoming game:

1. Find "starters" who are unavailable.  A starter is a player who, in the games he played this
   season, accounted for at least `starter_min_share` of the team's volume (attempts / carries /
   targets).  Unavailable = P(out) > 0 from the injury report + roster status.
2. Split the team's games this season into
     with    - games where all the absent starters played
     without - games where all of them were absent
3. Project each healthy player's share of team volume
     renorm  = his share in the `with` games + the vacated share redistributed in proportion
               to (his share + a depth-chart "next man up" bonus)
     blended with his actual share in the `without` games (weight n_without / (n_without + 2)),
     so a role that has already existed for weeks is not double counted.
4. yards = team volume per game x projected share x yards-per-volume (shrunk to league average)
   x opponent adjustment (same defensive factor as Sheet 1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .config import Category
from .defense import shrink
from .slate import fmt_kick, fmt_opp, fmt_spread_total


def _names(*frames_cols) -> dict:
    out = {}
    for df, idc, namec in frames_cols:
        if df is not None and len(df) and idc in df and namec in df:
            out.update(dict(zip(df[idc], df[namec])))
    return out


class _TeamVolume:
    """Week-by-player volume matrix for one team and one category."""

    def __init__(self, cur_t: pd.DataFrame, vol_col: str):
        v = cur_t.assign(vol=cur_t[vol_col].fillna(0))
        self.weeks = sorted(v.week.unique())
        self.mat = (v.pivot_table(index="week", columns="player_id", values="vol", aggfunc="sum")
                    .reindex(self.weeks).fillna(0.0))
        self.team_vol = self.mat.sum(axis=1)             # all positions
        self.pos = v.groupby("player_id").position.last()

    def share(self, pid, weeks) -> float:
        if not weeks or pid not in self.mat.columns:
            return 0.0
        den = self.team_vol.loc[weeks].sum()
        return float(self.mat.loc[weeks, pid].sum() / den) if den > 0 else 0.0

    def active_weeks(self, pid) -> list:
        if pid not in self.mat.columns:
            return []
        s = self.mat[pid]
        return list(s.index[s > 0])

    def missed_streak(self, pid) -> int:
        """Consecutive most-recent team games with no volume."""
        if pid not in self.mat.columns:
            return len(self.weeks)
        n = 0
        for w in reversed(self.weeks):
            if self.mat.loc[w, pid] > 0:
                break
            n += 1
        return n


def _scenario(tv: _TeamVolume, cat: Category, absent: list, healthy: list, depth_rank: dict):
    """Projected share of team volume for each healthy player when `absent` starters are out.

    Returns (shares dict, n_with, n_without).
    """
    if not absent:
        allw = tv.weeks
        return {j: tv.share(j, allw) for j in healthy}, len(allw), 0
    with_w = [w for w in tv.weeks if all(tv.mat.loc[w].get(a, 0) > 0 for a in absent)]
    wo_w = [w for w in tv.weeks if all(tv.mat.loc[w].get(a, 0) <= 0 for a in absent)]
    s_wo = {j: tv.share(j, wo_w) for j in healthy}
    if not with_w:                                       # starter hasn't played this season
        return s_wo, 0, len(wo_w)
    s_with = {j: tv.share(j, with_w) for j in healthy}
    vacated = sum(tv.share(a, with_w) for a in absent)

    bonus = C.DEPTH_BONUS.get(cat.key, {})
    if cat.redistribute == "group":
        pool = healthy
    else:                                                # every teammate who gets volume
        pool = list(dict.fromkeys([j for j in tv.mat.columns if j not in absent] + healthy))
    weight = {}
    for j in pool:
        weight[j] = (s_with[j] if j in s_with else tv.share(j, with_w)) \
            + (bonus.get(depth_rank.get(j, 99), 0.0) if j in healthy else 0.0)
    tot = sum(weight.values())
    ren = {j: s_with[j] + (vacated * weight.get(j, 0.0) / tot if tot > 0 else 0.0) for j in healthy}

    if not wo_w:
        return ren, len(with_w), 0
    lam = len(wo_w) / (len(wo_w) + C.WITHOUT_SAMPLE_PRIOR)
    return {j: lam * s_wo[j] + (1 - lam) * ren[j] for j in healthy}, len(with_w), len(wo_w)


def backup_table(cat: Category, stats, prev_stats, ratings, slate, depth, roster, pout_by_week,
                 injuries_names=None) -> pd.DataFrame:
    cur = stats.copy()
    cur["vol"] = cur[cat.volume].fillna(0)
    allseasons = pd.concat([cur, prev_stats], ignore_index=True) if len(prev_stats) else cur
    g = allseasons[allseasons.position.isin(cat.positions) & (allseasons[cat.volume].fillna(0) > 0)]
    lg_ypv = g[cat.yards].sum() / g[cat.volume].sum()
    by_player = g.groupby("player_id").agg(y=(cat.yards, "sum"), v=(cat.volume, "sum"))
    team_week_vol = cur.groupby(["team", "week"]).vol.sum()
    lg_team_pg = team_week_vol.mean()

    names = _names((stats, "player_id", "player_display_name"), (depth, "gsis_id", "player_name"),
                   (roster, "gsis_id", "full_name"), (injuries_names, "gsis_id", "full_name"))
    roster_status = dict(zip(roster.gsis_id, roster.status))
    rank_by_def = ratings.set_index("defense")

    depth_g = depth[depth.pos_abb.isin(cat.positions)]
    out_rows = []
    for sl in slate.itertuples():
        T, W = sl.team, sl.week
        cur_t = cur[cur.team == T]
        if cur_t.empty:
            continue
        tv = _TeamVolume(cur_t, cat.volume)
        po = pout_by_week.get(W)
        pmap = dict(zip(po.gsis_id, zip(po.p_out, po.label))) if po is not None and len(po) else {}

        d_t = depth_g[depth_g.team == T]
        depth_rank = d_t.groupby("gsis_id").pos_rank.min().to_dict()
        group_ids = set(tv.pos[tv.pos.isin(cat.positions)].index) | set(depth_rank)
        # only players who can actually play for this team
        members = [j for j in group_ids if roster_status.get(j, "ACT") not in ("CUT", "RET", "EXE")]

        # --- who is out? (starter-level players only) ---------------------------------------
        certain, maybe = [], []
        for j in members:
            p = pmap.get(j, (0.0, ""))[0]
            if p <= 0:
                continue
            act = tv.active_weeks(j)
            if not act or tv.share(j, act) < cat.starter_min_share:
                continue
            (certain if p >= 0.99 else maybe).append(j)
        if not certain and not maybe:
            continue

        absent_all = set(certain) | set(maybe)
        healthy = [j for j in members if j not in absent_all and pmap.get(j, (0.0, ""))[0] < 0.99]

        s_in, _, _ = _scenario(tv, cat, certain, healthy, depth_rank)
        s_out, n_with, n_wo = _scenario(tv, cat, certain + maybe, healthy, depth_rank)
        s_base, _, _ = _scenario(tv, cat, [], healthy, depth_rank)

        p_q = 1.0 - np.prod([1 - pmap[j][0] for j in maybe]) if maybe else 0.0
        p_vac = 1.0 if certain else p_q

        tv_pg = shrink(tv.team_vol.mean(), len(tv.weeks), lg_team_pg, C.TEAM_VOL_PRIOR_GAMES)
        f = rank_by_def.factor.get(sl.opp, 1.0)
        adj = 1 + C.MATCHUP_BETA * (f - 1)

        streaks = [tv.missed_streak(a) for a in certain + maybe]
        streak = min(streaks) if streaks else 0

        starters_txt = "; ".join(
            f"{names.get(a, a)} {pmap[a][1]}" for a in sorted(certain + maybe,
                                                              key=lambda x: -pmap[x][0]))
        for j in healthy:
            dr = depth_rank.get(j, 99)
            if dr < cat.backup_min_depth:
                continue
            base_vol = tv_pg * s_base[j]
            g_ = cat.uplift_shrink
            vol_in = base_vol + g_ * (tv_pg * s_in[j] - base_vol)
            vol_out = base_vol + g_ * (tv_pg * s_out[j] - base_vol)
            vol_exp = (1 - p_q) * vol_in + p_q * vol_out if maybe else vol_in
            if vol_out - base_vol < cat.min_uplift or vol_out < cat.min_proj_vol:
                continue
            y, v = by_player.y.get(j, 0.0), by_player.v.get(j, 0.0)
            ypv = shrink(y / v if v else np.nan, v, lg_ypv, cat.ypv_prior_n)
            proj_out = vol_out * ypv * adj
            proj_exp = vol_exp * ypv * adj
            out_rows.append(dict(
                player_id=j, name=names.get(j, j), team=T, opp=sl.opp, home=sl.home, week=W,
                kickoff=sl.kickoff, spread=sl.spread, ou=sl.ou,
                inj=pmap.get(j, (0, ""))[1],
                role=f"{cat.key}{dr}" if dr < 99 else f"{cat.key}?",
                starters_out=starters_txt, p_out=p_vac, streak=streak,
                n_with=n_with, n_without=n_wo,
                base_vol=base_vol, last_vol=float(tv.mat.iloc[-1].get(j, 0.0)),
                proj_vol=vol_out, ypv=ypv,
                opp_rank=rank_by_def["rank"].get(sl.opp), opp_vs_lg=f - 1,
                proj_if_out=proj_out, proj_exp=proj_exp))
    df = pd.DataFrame(out_rows)
    if df.empty:
        return df
    df["opp_txt"] = df.apply(fmt_opp, axis=1)
    df["kick_txt"] = df.kickoff.map(fmt_kick)
    df["spr_tot"] = [fmt_spread_total(s, o) for s, o in zip(df.spread, df.ou)]
    df["fresh"] = df.streak < C.ESTABLISHED_AFTER
    return (df.sort_values(["fresh", "p_out", "proj_exp"], ascending=[False, False, False])
              .reset_index(drop=True))
