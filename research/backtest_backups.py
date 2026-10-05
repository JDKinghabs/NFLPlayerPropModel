"""Walk-forward test of the Sheet 2 mechanism using the production code.

For every week W >= 4 of a past season we pretend it is the day before kickoff:
only games before W are visible, the injury report for W is the real final report, and
we ask the model for backups whose starter is listed OUT.  We then compare the projected
workload / yards to what actually happened, against the naive alternative of "he keeps
getting his season-average workload".

Depth charts are not archived per week, so depth rank is proxied by season-to-date volume rank.

    python research/backtest_backups.py 2024 2025
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from props import config as C                                   # noqa: E402
from props.availability import p_out_table                      # noqa: E402
from props.backups import backup_table                          # noqa: E402
from props.data import STAT_COLS, cached                        # noqa: E402
from props.defense import defense_ratings                       # noqa: E402
from props.slate import _kickoff, _team_rows                    # noqa: E402
from props.snaps import prepare_snaps                           # noqa: E402


def load(year):
    d = pd.read_csv(cached(f"stats_player/stats_player_week_{year}.csv", False),
                    usecols=lambda c: c in STAT_COLS)
    return d[d.season_type == "REG"].copy()


def proxy_depth(stats, cat):
    """Depth rank proxy: season-to-date volume rank within team and position group."""
    s = stats[stats.position.isin(cat.positions)]
    v = s.groupby(["team", "player_id"])[cat.volume].sum().reset_index()
    v["pos_rank"] = v.groupby("team")[cat.volume].rank(ascending=False, method="first").astype(int)
    return v.rename(columns={"player_id": "gsis_id"}).assign(pos_abb=cat.positions[0])[
        ["team", "gsis_id", "pos_abb", "pos_rank"]]


def load_snaps(season):
    snap = pd.read_csv(cached(f"snap_counts/snap_counts_{season}.csv", False))
    ro = pd.read_csv(cached(f"rosters/roster_{season}.csv", False), usecols=["gsis_id", "pfr_id"])
    sn = prepare_snaps(snap, ro)
    return sn


def run(season: int):
    cur_all, prev = load(season), load(season - 1)
    games = pd.read_csv(cached("schedules/games.csv", True))
    games = games[(games.season == season) & (games.game_type == "REG")].copy()
    inj = pd.read_csv(cached(f"injuries/injuries_{season}.csv", False))
    roster = pd.DataFrame(columns=["team", "position", "full_name", "gsis_id", "status", "week"])
    snaps_all = load_snaps(season)
    rows = []
    for W in range(4, 19):
        gw = games[games.week == W]
        if gw.empty:
            continue
        gw = gw.assign(kickoff=_kickoff(gw))
        slate = _team_rows(gw)
        seen = cur_all[cur_all.week < W]
        pout = {W: p_out_table(inj, roster, W, seen)}
        actual = cur_all[cur_all.week == W]
        for k, cat in C.CATS.items():
            ratings = defense_ratings(seen, prev, cat)
            bt = backup_table(cat, seen, prev, ratings, slate, proxy_depth(seen, cat), roster, pout,
                              injuries_names=inj, snaps=snaps_all[snaps_all.week < W])
            if bt.empty:
                continue
            bt = bt[bt.p_out >= 0.99]                     # starter definitively listed Out
            a = actual.set_index("player_id")
            for r in bt.itertuples():
                if r.player_id in a.index:
                    act_v, act_y = a.loc[r.player_id, cat.volume], a.loc[r.player_id, cat.yards]
                else:
                    act_v, act_y = 0.0, 0.0
                rows.append(dict(season=season, week=W, cat=k, name=r.name, team=r.team,
                                 base_vol=r.base_vol, proj_vol=r.proj_vol, act_vol=act_v,
                                 proj_yds=r.proj_if_out, act_yds=act_y, ypv=r.ypv))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    seasons = [int(x) for x in sys.argv[1:]] or [2024, 2025]
    df = pd.concat([run(s) for s in seasons], ignore_index=True)
    df["naive_yds"] = df.base_vol * df.ypv
    for k, g in df.groupby("cat"):
        # keep players who actually played (a prop only exists for a player who is active)
        gp = g[g.act_vol > 0]
        print(f"\n== {k}: {len(g)} backup-situations, {len(gp)} where the backup played")
        for lab, sub in (("all listed", g), ("played", gp)):
            print(f"  [{lab:10s}] volume MAE: model={np.mean(abs(sub.proj_vol - sub.act_vol)):.2f}  "
                  f"naive(season avg)={np.mean(abs(sub.base_vol - sub.act_vol)):.2f}   "
                  f"bias: model={np.mean(sub.proj_vol - sub.act_vol):+.2f} naive={np.mean(sub.base_vol - sub.act_vol):+.2f}"
                  f"   | mean actual={sub.act_vol.mean():.2f}")
            print(f"  [{lab:10s}] yards  MAE: model={np.mean(abs(sub.proj_yds - sub.act_yds)):.1f}  "
                  f"naive={np.mean(abs(sub.naive_yds - sub.act_yds)):.1f}   "
                  f"bias: model={np.mean(sub.proj_yds - sub.act_yds):+.1f} naive={np.mean(sub.naive_yds - sub.act_yds):+.1f}"
                  f"   | mean actual={sub.act_yds.mean():.1f}")

    # ---- is the predicted *uplift* real?  (the claim Sheet 2 rests on) ----------------------
    print("\n==== Uplift check (backup played): does proj - base predict act - base? ====")
    for k, g in df[df.act_vol > 0].groupby("cat"):
        up_p, up_a = g.proj_vol - g.base_vol, g.act_vol - g.base_vol
        slope = np.polyfit(up_p, up_a, 1)[0] if up_p.std() > 0 else float("nan")
        rm = lambda e: float(np.sqrt(np.mean(e ** 2)))                       # noqa: E731
        print(f"  {k}: n={len(g)}  mean predicted uplift={up_p.mean():+.2f}  mean realised uplift={up_a.mean():+.2f}"
              f"  slope={slope:.2f}  corr(proj,act)={np.corrcoef(g.proj_vol, g.act_vol)[0,1]:.2f}"
              f" vs corr(base,act)={np.corrcoef(g.base_vol, g.act_vol)[0,1]:.2f}"
              f"  | vol RMSE model={rm(g.proj_vol-g.act_vol):.2f} naive={rm(g.base_vol-g.act_vol):.2f}"
              f"  | yds RMSE model={rm(g.proj_yds-g.act_yds):.1f} naive={rm(g.naive_yds-g.act_yds):.1f}")
